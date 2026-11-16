#!/bin/bash
# The commands of aur-packages not ported to Python yet (aur_packages/), which ./aur-packages runs.
# Manages the AUR packages of this repository, the top-level folders with a PKGBUILD: as
# ./aur-packages in a checkout, or as aur-packages on PATH. See ./aur-packages help.

set -euo pipefail

# A checkout of this repository: a folder with this script and the package template
is_checkout() {
  [[ -f "$1/aur-packages" && -d "$1/templates/package" ]]
}

# The checkout to work on. Run from a checkout (./aur-packages, or its path), that one. Run from
# elsewhere, e.g. from a symlink or a copy on PATH, the checkout of the current directory, else
# $AUR_PACKAGES_HOME, else the one the symlink points into; then that checkout's own script runs, so
# the commands always match the checkout's version.
self=$(realpath "$0")
if is_checkout "$(dirname "$0")"; then
  root=$(dirname "$self")
else
  if top=$(git rev-parse --show-toplevel 2>/dev/null) && is_checkout "$top"; then
    root=$top
  elif [[ -n "${AUR_PACKAGES_HOME:-}" ]]; then
    if ! is_checkout "$AUR_PACKAGES_HOME"; then
      echo "${0##*/}: AUR_PACKAGES_HOME isn't a checkout of the AUR packages: $AUR_PACKAGES_HOME" >&2
      exit 1
    fi
    root=$AUR_PACKAGES_HOME
  elif is_checkout "$(dirname "$self")"; then
    root=$(dirname "$self")
  else
    echo "${0##*/}: not in a checkout of the AUR packages, set AUR_PACKAGES_HOME to one" >&2
    exit 1
  fi
  root=$(realpath "$root")
  # Relative paths in the arguments (--repo, commit-msg's file) are relative to where it was called
  export AUR_PACKAGES_CWD=$PWD
  exec "$root/aur-packages" "$@"
fi
# Where relative paths in the arguments start from
cwd=${AUR_PACKAGES_CWD:-$PWD}
unset AUR_PACKAGES_CWD
cd "$root" || exit

# Names the build graph resolves to another package than the one of that name, set by build's
# --dotnet-bin and --libs-bin to pick the -bin variant of a selector package
declare -A build_alias=()
# build_edges, once per run, for build_multilib
build_edges_cache=''

# The folders of the packages: the AUR packages at the top level, then local/ (packages of ours that
# aren't on the AUR) and overrides/ (Arch Linux's packages with changes of ours), which are built and
# checked, but never published to the AUR
package_dirs() {
  local pkgbuild
  for pkgbuild in */PKGBUILD local/*/PKGBUILD overrides/*/PKGBUILD; do
    [[ -f "$pkgbuild" ]] && printf '%s
' "${pkgbuild%/PKGBUILD}"
  done
}

# The folder of a package, by its folder or its name (e.g. ghidra for overrides/ghidra)
package_dir() {
  local name=${1%/} dir
  for dir in "$name" "local/$name" "overrides/$name"; do
    if [[ -f "$dir/PKGBUILD" ]]; then
      printf '%s
' "$dir"
      return 0
    fi
  done
  return 1
}

# Sets $selected to the given packages, or all of them (--aur: only the AUR packages, the default
# list as well as the given ones). Fails for folders that aren't packages.
select_packages() {
  local package dir aur_only=false
  selected=()
  if [[ "${1-}" == --aur ]]; then
    aur_only=true
    shift
  fi
  if (($#)); then
    for package; do
      if ! dir=$(package_dir "$package"); then
        echo "Not a package: $package" >&2
        return 1
      fi
      if [[ "$aur_only" == true && "$dir" == */* ]]; then
        echo "Not an AUR package: $dir (local/ and overrides/ aren't published to the AUR)" >&2
        return 1
      fi
      selected+=("$dir")
    done
  elif [[ "$aur_only" == true ]]; then
    for package in */PKGBUILD; do
      selected+=("${package%/PKGBUILD}")
    done
  else
    mapfile -t selected < <(package_dirs)
  fi
}

# Sets $checked to the selected packages with update checks, VCS packages don't have them
select_checked_packages() {
  local package
  local -a selected
  select_packages "$@"
  checked=()
  for package in "${selected[@]}"; do
    [[ -f "$package/.nvchecker.toml" ]] && checked+=("$package")
  done
}

cmd_updates() {
  local -a checked
  require updates pkgctl:devtools nvchecker:nvchecker jq:jq
  if [[ "${1-}" == --state ]]; then
    shift
    if [[ "${1-}" == --retry ]]; then
      shift
      updates_state true "$@"
    else
      updates_state false "$@"
    fi
    return
  fi
  select_checked_packages "$@"
  ((${#checked[@]})) || return 0
  pkgctl version check "${checked[@]}"
}

# The state file of updates --state, which the tray icon (aur-packages-tray) watches
updates_state_file=${XDG_STATE_HOME:-$HOME/.local/state}/aur-packages/updates.json

# The transient units of the retries after a rate limit, aur-packages-updates-retry-<time>.timer
updates_retry_unit=aur-packages-updates-retry

# Prints the GitHub token of nvchecker's keyfile, else the one gh is logged in with (gh auth token),
# nothing without either
github_token() {
  local keyfile=${XDG_CONFIG_HOME:-$HOME/.config}/nvchecker/keyfile.toml token=''
  if [[ -f "$keyfile" ]]; then
    token=$(python3 -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb")).get("keys", {}).get("github", ""))' \
      "$keyfile" 2>/dev/null || true)
  fi
  if [[ -z "$token" ]] && command -v gh >/dev/null; then
    token=$(gh auth token --hostname github.com 2>/dev/null || true)
  fi
  printf '%s\n' "$token"
}

# Prints when GitHub's rate limit resets, in seconds since the epoch, from its rate_limit endpoint (which
# doesn't count against the limit), with the token of nvchecker's keyfile if there is one; the time an
# exhausted limit resets, else now, as the limit has room again
github_rate_limit_reset() {
  local token config=''
  token=$(github_token)
  # On stdin rather than the command line, where other users could read it
  [[ -z "$token" ]] || config="header = \"Authorization: Bearer $token\""
  curl -fsS --max-time 30 -K - https://api.github.com/rate_limit <<<"$config" |
    jq -r '[.resources[] | select(.remaining == 0) | .reset] | max // now | floor'
}

# Checks the packages like updates and writes the result to $updates_state_file, as JSON: the time of
# the check, the checkout, the outdated packages (package, current and new version), the packages whose
# check failed, those that hit GitHub's rate limit with the time they're checked again, and an error if
# the whole check failed.
# - Packages that weren't checked, or whose check failed, keep the entries of earlier checks, so a rate
#   limit or a missing network doesn't make updates disappear, and packages given check only those.
# - With --retry (the service of tray install), a transient timer of systemd checks the rate-limited
#   packages again a minute after the limit resets; a check run by hand neither leaves timers behind
#   nor cancels them.
# - If no package could be checked, the error says so, and the command fails.
# Written atomically under a lock, so the tray never reads half a file and checks don't overlap.
updates_state() {
  local dir output errors status=0 previous='null' tmp state pending reset lock notes
  local -a checked retry environment=(--setenv=PATH)
  local schedule=$1
  shift
  select_checked_packages "$@"
  dir=${updates_state_file%/*}
  mkdir -p "$dir"
  exec {lock}>"$dir/.updates.lock"
  flock "$lock"
  if [[ -f "$updates_state_file" ]] && jq -e . "$updates_state_file" >/dev/null 2>&1; then
    previous=$(<"$updates_state_file")
  fi
  errors=$(mktemp)
  # shellcheck disable=SC2064 # expand $errors now, when the trap is set
  trap "rm -f '$errors'; exec $lock>&-" RETURN
  # JSON lists the outdated packages and the failed checks, pkgctl exits with 0 either way
  if ! output=$(pkgctl version check --json "${checked[@]}" 2>"$errors") || ! jq -e 'type == "array"' <<<"$output" >/dev/null 2>&1; then
    output=$(jq -n --arg error "pkgctl version check failed: $(tail -n 1 "$errors")" '{error: $error}')
    status=1
  else
    output=$(jq -n --argjson results "$output" --argjson total "${#checked[@]}" '
      # A 403 or 429 of GitHub'"'"'s API, or nvchecker saying so
      def rate_limited: test("rate limit"; "i") or (test("api\\.github\\.com") and test("(HTTPError\\(|HTTP )(403|429)"));
      # tornado'"'"'s HTTPError shown with its response, which takes a screen: its code, reason and URL
      def short:
        if test("HTTPError\\([0-9]+, ") then
          capture("HTTPError\\((?<code>[0-9]+), '"'"'(?<reason>[^'"'"']*)'"'"'") as $error
          | ((capture("effective_url='"'"'(?<url>[^'"'"']*)'"'"'") | " (\(.url))") // "") as $url
          | "HTTP \($error.code) \($error.reason)\($url)"
        else split("\n")[0] | sub("^unexpected error happened: "; "") end;
      [$results[] | select(.status == "failure")] as $failed
      | {
          results: true,
          updates: [$results[] | select(.status == "success" and .out_of_date)
            | {package: .pkgbase, current: .local_version, new: .upstream_version}],
          failed: [$failed[].pkgbase],
          failures: [$failed[] | select(.message // "" | rate_limited | not)
            | {package: .pkgbase, message: (.message // "failed" | short)}],
          rate_limited: [$failed[] | select(.message // "" | rate_limited) | .pkgbase],
          # Not when only the rate limit stopped them: they wait for the retry
          error: (if $total > 0 and ($failed | length) == $total and any($failed[]; .message // "" | rate_limited | not)
            then "No package could be checked, e.g. without a network connection" else null end)
        }')
    jq -e '.error == null' <<<"$output" >/dev/null || status=1
  fi
  # The packages by name (pkgbase, their folder's name), as pkgctl reports them: by folder, the ones in
  # local/ and overrides/ never matched, so their old entries stayed after later checks
  state=$(jq -n --argjson new "$output" --argjson previous "$previous" --arg checked "$(date --iso-8601=seconds)" \
    --arg checkout "$root" --args '
    ($previous // {}) as $previous
    | $ARGS.positional as $checked_packages
    # What this check found out: the packages it checked, unless their check failed
    | (if $new.results then $checked_packages - $new.failed else [] end) as $known
    | (if $new.results then $checked_packages else [] end) as $tried
    | ($previous.rate_limited.packages // []) as $waiting
    | {
        checked: $checked,
        checkout: $checkout,
        error: $new.error,
        updates: (($new.updates // []) + [$previous.updates // [] | .[] | select(.package as $p | $known | index($p) | not)]
          | sort_by(.package)),
        failures: (($new.failures // []) + [$previous.failures // [] | .[] | select(.package as $p | $tried | index($p) | not)]
          | sort_by(.package)),
        rate_limited: {
          packages: (($new.rate_limited // []) + [$waiting[] | select(. as $p | $tried | index($p) | not)] | unique),
          retry: null
        }
      }' "${checked[@]##*/}")
  # The notes on the maintainers on the AUR (maintainers --aur), of all packages; without an answer of the
  # AUR, the previous ones
  if notes=$("$root/aur-packages" maintainers --aur --json 2>/dev/null); then
    state=$(jq --argjson notes "$notes" '.maintainers = $notes' <<<"$state")
  else
    state=$(jq --argjson previous "$previous" '.maintainers = (($previous // {}).maintainers // [])' <<<"$state")
  fi
  mapfile -t retry < <(jq -r '.rate_limited.packages[]' <<<"$state")
  # Only one retry is pending, the one for the packages that wait now
  if [[ "$schedule" == true ]]; then
    systemctl --user stop "$updates_retry_unit-*.timer" >/dev/null 2>&1 || true
  fi
  if ((${#retry[@]})); then
    reset=$(github_rate_limit_reset) || reset=$(($(date +%s) + 3600 - 60))
    pending=$(date --date="@$((reset + 60))" --iso-8601=seconds)
    state=$(jq --arg retry "$pending" '.rate_limited.retry = $retry' <<<"$state")
    if [[ "$schedule" == true ]]; then
      # With the environment of this check, e.g. the same state file
      [[ -z "${XDG_STATE_HOME:-}" ]] || environment+=(--setenv=XDG_STATE_HOME)
      systemd-run --user --quiet --collect --unit="$updates_retry_unit-$reset" --on-active=$((reset + 60 - $(date +%s))) \
        --timer-property=AccuracySec=1min --property=Type=oneshot --description="Check the AUR packages that hit GitHub's rate limit" \
        "${environment[@]}" /usr/bin/python3 "$root/aur-packages" updates --state --retry "${retry[@]}" ||
        echo "Couldn't schedule checking the rate-limited packages again" >&2
    fi
  fi
  tmp=$(mktemp "$dir/.updates.json.XXXXXX")
  printf '%s\n' "$state" >"$tmp"
  mv "$tmp" "$updates_state_file"
  jq -r '(.updates[] | "\(.package) \(.current) -> \(.new)"), (.failures[] | "\(.package): check failed: \(.message)"),
    (.rate_limited | select(.packages != []) | "GitHub'"'"'s rate limit, checked again at \(.retry): \(.packages | join(" "))"),
    (.maintainers[] | "\(.folder): \(.message)"),
    (.error // empty | "Error: \(.)")' "$updates_state_file"
  return "$status"
}

# Prints the full version of the .SRCINFO on stdin, e.g. a package's file in the working tree
srcinfo_text_version() {
  local srcinfo epoch pkgver pkgrel
  srcinfo=$(cat)
  epoch=$(sed -n -E 's/^\tepoch = //p' <<<"$srcinfo")
  pkgver=$(sed -n -E 's/^\tpkgver = //p' <<<"$srcinfo")
  pkgrel=$(sed -n -E 's/^\tpkgrel = //p' <<<"$srcinfo")
  printf '%s\n' "${epoch:+$epoch:}$pkgver-$pkgrel"
}

cmd_upgrade() {
  local package pin name cur new
  local -a checked changed=() pins unresolved=()
  require upgrade pkgctl:devtools nvchecker:nvchecker updpkgsums:pacman-contrib shfmt:shfmt curl:curl jq:jq
  select_checked_packages "$@"
  ((${#checked[@]})) || return 0
  pkgctl version upgrade "${checked[@]}"

  mapfile -t changed < <(git diff --name-only -- "${checked[@]/%//PKGBUILD}")
  for package in "${changed[@]}"; do
    package=${package%/PKGBUILD}
    # pkgctl bumps pkgver but leaves the pins (_commit, or what _pins_lookup prints) at the old
    # release, so move them to the new version's (see cmd_commits) before the checksums are taken, so
    # the sources and sums match the new version rather than the old commits
    pins=()
    mapfile -t pins < <(resolve_pins "$package")
    for pin in "${pins[@]}"; do
      name=${pin%% *} new=${pin#"$name"}
      new=${new# }
      cur=$(pin_value "$package" "$name")
      if [[ -z "$new" || "$new" == null ]]; then
        echo "  couldn't resolve $name of $package's new version, left at $(short_pin "$cur")" >&2
        unresolved+=("$package $name")
      elif [[ "$new" != "$cur" ]]; then
        set_pin "$package" "$name" "$new"
        echo "  $name $(short_pin "$cur") -> $(short_pin "$new")"
      fi
    done
    if ((${#pins[@]})); then update_checksums "$package"; fi
    # updpkgsums aligns the checksums its own way
    shfmt --write "$package/PKGBUILD"
    (cd "$package" && makepkg --printsrcinfo >.SRCINFO)
    echo "Upgraded $package"
  done
  # The version is upgraded, but a pin still names the old one's sources: not done yet
  if ((${#unresolved[@]})); then
    echo "Pins left at the old version, e.g. after GitHub's rate limit; run ./aur-packages commits --update" \
      "on the packages later, or set them by hand:" >&2
    printf '  %s\n' "${unresolved[@]}" >&2
    return 1
  fi
}

# Fails, naming the packages to install, unless the commands given as command:package are installed,
# before a command does anything; $1 says what needs them
require() {
  local what=$1 tool
  local -a missing=()
  local -A seen=()
  shift
  for tool; do
    [[ -z "${seen[$tool]-}" ]] || continue
    seen[$tool]=1
    if ! command -v "${tool%%:*}" >/dev/null; then missing+=("${tool%%:*} (${tool#*:})"); fi
  done
  ((${#missing[@]})) || return 0
  echo "$what: these commands aren't installed: $(
    IFS=,
    printf '%s' "${missing[*]}" | sed 's/,/, /g'
  )" >&2
  return 1
}

# The application ID of aur-packages-tray, its name on the session bus
tray_app_id=info.rev_crew.AurPackagesTray

# Installs the daily update check (the user units of systemd/, linked from this checkout, which a
# drop-in points at) and the tray icon's autostart entry, then starts both; or removes them again
cmd_tray() {
  local units=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
  local autostart=${XDG_CONFIG_HOME:-$HOME/.config}/autostart/aur-packages-tray.desktop
  local service=aur-packages-updates.service timer=aur-packages-updates.timer value exec
  case "${1-}" in
    install)
      if ! python3 -c 'from gi.repository import Gio' 2>/dev/null; then
        echo "The tray icon needs python-gobject, the check is installed anyway" >&2
      fi
      if ! command -v wl-copy >/dev/null; then
        echo "Copying the upgrade command needs wl-clipboard" >&2
      fi
      # --force replaces the links of another checkout
      systemctl --user link --force "$root/systemd/$service" "$root/systemd/$timer"
      # systemd unquotes the value, and expands specifiers (%)
      value=$root
      value=${value//\\/\\\\}
      value=${value//\"/\\\"}
      value=${value//%/%%}
      mkdir -p "$units/$service.d"
      cat >"$units/$service.d/checkout.conf" <<EOF
# Installed by ./aur-packages tray install: the checkout whose packages are checked
[Service]
Environment="AUR_PACKAGES_HOME=$value"
EOF
      systemctl --user daemon-reload
      systemctl --user enable --now "$timer"
      # The Exec key quotes the path for the desktop entry's argument syntax, and escapes backslashes
      # once more as a string value
      exec=$root/aur-packages-tray
      exec=${exec//\\/\\\\}
      exec=${exec//\"/\\\"}
      exec=${exec//\`/\\\`}
      exec=${exec//\$/\\\$}
      exec=${exec//\\/\\\\}
      mkdir -p "${autostart%/*}"
      cat >"$autostart" <<EOF
[Desktop Entry]
Type=Application
Name=AUR package updates
Comment=Tray icon of the update check of the AUR packages, installed by ./aur-packages tray install
Icon=system-software-update
Exec="$exec"
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF
      echo "Installed the units of $root/systemd, $units/$service.d/checkout.conf and $autostart"
      # A first result for the tray, and the tray itself in a graphical session
      systemctl --user start --no-block "$service"
      if [[ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]]; then
        setsid -f "$root/aur-packages-tray" >/dev/null 2>&1 </dev/null
        echo "Started the tray icon"
      fi
      ;;
    remove)
      systemctl --user disable --now "$timer" 2>/dev/null || true
      systemctl --user stop "$service" "$updates_retry_unit-*.timer" 2>/dev/null || true
      # disable removes the links of systemctl link as well, these are what might be left
      rm -f "$units/$service" "$units/$timer"
      rm -rf "$units/$service.d"
      systemctl --user daemon-reload
      rm -f "$autostart"
      # The tray quits by its action, if it's running
      gdbus call --session --dest "$tray_app_id" --object-path "/${tray_app_id//.//}" \
        --method org.freedesktop.Application.ActivateAction quit '[]' '{}' >/dev/null 2>&1 || true
      echo "Removed the update check and the tray icon; the last result stays in ${updates_state_file%/*}"
      ;;
    *)
      echo "Usage: aur-packages tray install|remove" >&2
      return 1
      ;;
  esac
}

# Prints "depdir<TAB>pkgdir" for every build dependency (depends/makedepends/checkdepends, of any
# architecture) that resolves to another package in this repository, from the .SRCINFO files
build_edges() {
  local s d line key name
  local -A name2dir=() provider=()
  while IFS= read -r d; do
    s=$d/.SRCINFO
    while IFS= read -r line; do
      [[ "$line" == *" = "* ]] || continue
      key=${line%% = *}
      key=${key//[[:space:]]/}
      [[ "$key" == pkgname || "$key" == provides ]] || continue
      name=${line#* = }
      name=${name%%[<>=:]*}
      [[ -n "$name" ]] || continue
      # A package's own name wins over what others provide, e.g. dotnet-build-deps-10.0 over
      # the dotnet-build-deps-10.0-bin that provides it
      if [[ "$key" == pkgname ]]; then
        name2dir[$name]=$d
        unset "provider[$name]"
      elif [[ -z "${name2dir[$name]:-}" || -n "${provider[$name]:-}" ]]; then
        name2dir[$name]=$d
        provider[$name]=1
      fi
    done <"$s"
  done < <(package_dirs)
  for name in "${!build_alias[@]}"; do
    name2dir[$name]=${build_alias[$name]}
  done
  while IFS= read -r d; do
    s=$d/.SRCINFO
    while IFS= read -r line; do
      [[ "$line" == *" = "* ]] || continue
      key=${line%% = *}
      key=${key//[[:space:]]/}
      case "$key" in
        depends | makedepends | checkdepends | depends_* | makedepends_* | checkdepends_*) ;;
        *) continue ;;
      esac
      name=${line#* = }
      name=${name%%[<>=:]*}
      [[ -n "$name" ]] || continue
      if [[ -n "${name2dir[$name]:-}" && "${name2dir[$name]}" != "$d" ]]; then
        printf '%s\t%s\n' "${name2dir[$name]}" "$d"
      fi
    done <"$s"
  done < <(package_dirs) | sort -u
}

# Prints the dependencies of the given packages (depends, makedepends and checkdepends, also the
# architecture-specific ones) that only the AUR has: neither a package of this repository, by name or
# provides, nor the official repositories ($1, a pacman.conf of devtools, with the host's sync
# databases; without dependency checks, which would weigh in the host's installed packages) provide
# them, e.g. lasso for sogo, or the .NET SDK of a -bin selector
aur_only_deps() {
  local repoconf=$1 d line key name
  local -A ours=() wanted=()
  shift
  while IFS= read -r d; do
    while IFS= read -r line; do
      [[ "$line" == *" = "* ]] || continue
      key=${line%% = *}
      key=${key//[[:space:]]/}
      [[ "$key" == pkgname || "$key" == provides ]] || continue
      name=${line#* = }
      ours["${name%%[<>=:]*}"]=1
    done <"$d/.SRCINFO"
  done < <(package_dirs)
  for d; do
    while IFS= read -r line; do
      [[ "$line" == *" = "* ]] || continue
      key=${line%% = *}
      key=${key//[[:space:]]/}
      case "$key" in
        depends | makedepends | checkdepends | depends_* | makedepends_* | checkdepends_*) ;;
        *) continue ;;
      esac
      name=${line#* = }
      name=${name%%[<>=:]*}
      [[ -n "$name" && -z "${ours[$name]:-}" ]] || continue
      wanted[$name]=1
    done <"$d/.SRCINFO"
  done
  for name in "${!wanted[@]}"; do
    pacman --config "$repoconf" -Sddp --print-format %n "$name" >/dev/null 2>&1 || printf '%s\n' "$name"
  done | sort
}

# Succeeds if a package in the repository folder $1 is called $2 or provides it
repo_provides() {
  local file
  for file in "$1"/*.pkg.tar.zst; do
    [[ -f "$file" ]] || continue
    if bsdtar -xOf "$file" .PKGINFO | grep -qxE "(pkgname|provides) = ${2//./\\.}([<>=].*)?"; then
      return 0
    fi
  done
  return 1
}

# Prints the given root packages and all their repo-local dependencies, dependencies first
build_order() {
  local edges a b n d induced ordered
  local -a dlist queue
  local -A deps=() seen=()
  edges=$(build_edges)
  while IFS=$'\t' read -r a b; do
    if [[ -n "$b" ]]; then deps[$b]+="$a "; fi
  done <<<"$edges"
  queue=("$@")
  while ((${#queue[@]})); do
    n=${queue[0]}
    queue=("${queue[@]:1}")
    [[ -n "${seen[$n]:-}" ]] && continue
    seen[$n]=1
    read -ra dlist <<<"${deps[$n]:-}" || true
    for d in "${dlist[@]}"; do
      [[ -n "${seen[$d]:-}" ]] || queue+=("$d")
    done
  done
  induced=$(while IFS=$'\t' read -r a b; do
    if [[ -n "${seen[$a]:-}" && -n "${seen[$b]:-}" ]]; then printf '%s\t%s\n' "$a" "$b"; fi
  done <<<"$edges")
  ordered=$(tsort <<<"$induced")
  if [[ -n "$ordered" ]]; then printf '%s\n' "$ordered"; fi
  # Packages with no repo-local dependency edges don't appear above; their order is free
  for n in "${!seen[@]}"; do
    grep -qxF "$n" <<<"$ordered" || printf '%s\n' "$n"
  done
}

# Prints the root packages of a build template, or returns 1 if the name isn't one
build_template() {
  case "$1" in
    powershell-core)
      printf '%s\n' powershell
      ;;
    powershell-full)
      printf '%s\n' powershell powershell-editor-services powershell-dsc vscode-powershell \
        powershell-mmi powershell-pester-4 powershell-powershellget-v3
      ;;
    *)
      return 1
      ;;
  esac
}

# Prints the architectures of a package, from its .SRCINFO
build_arches() {
  sed -n -E 's/^\s*arch = //p' "$1/.SRCINFO"
}

# Succeeds if a package builds against the multilib repository: it or a package of this repository
# it depends on, which the container installs with its dependencies, depends on 32-bit libraries,
# the lib32-* packages only multilib has (e.g. a SourceMod plugin, through sourcemod). Like Arch's
# multilib packages (pkgctl build --repo multilib), it builds in a container of its own with
# multilib and its toolchain (multilib-devel).
build_multilib() {
  local pkg dep dependent
  local -a queue=("$1")
  local -A seen=()
  if [[ -z "$build_edges_cache" ]]; then
    build_edges_cache=$(build_edges)
  fi
  while ((${#queue[@]})); do
    pkg=${queue[0]}
    queue=("${queue[@]:1}")
    [[ -n "${seen[$pkg]:-}" ]] && continue
    seen[$pkg]=1
    grep -q -E '^\s*(depends|makedepends|checkdepends)(_x86_64)? = lib32-' "$pkg/.SRCINFO" && return 0
    while IFS=$'\t' read -r dep dependent; do
      if [[ "$dependent" == "$pkg" ]]; then queue+=("$dep"); fi
    done <<<"$build_edges_cache"
  done
  return 1
}

# Prints a pacman.conf of devtools ($1, e.g. extra.conf) with the private repository $2 at $3 added
# first, so its freshly built packages take precedence over the same ones in the other repositories
devtools_pacman_conf() {
  awk -v name="$2" -v root="$3" '
    /^\[/ && $0 != "[options]" && !inserted {
      printf "[%s]\nSigLevel = Never\nServer = file://%s\n\n", name, root
      inserted = 1
    }
    { print }
  ' "/usr/share/devtools/pacman.conf.d/$1"
}

# Prints the names of the packages a package directory builds, several for a split package, from its
# .SRCINFO
build_pkgnames() {
  sed -n -E 's/^pkgname = //p' "$1/.SRCINFO"
}

# The key of the Arch Linux ARM build system, which signs its images
alarm_key=68B3537F39A313B3E574D06777193F152BDBE6A6

# Sets up the Arch Linux ARM root file system of the aarch64 builds in $1/root, if it isn't there yet:
# the native builds run in it (under QEMU, with qemu-user-static-binfmt), the cross builds compile
# against it. From the latest image of archlinuxarm.org, checked against the key of its build system,
# without the kernel and firmware, which a container doesn't need, and with base-devel.
alarm_root() {
  local dir=$1 cache=${XDG_CACHE_HOME:-$HOME/.cache}/aur-packages/alarm
  local image=ArchLinuxARM-aarch64-latest.tar.gz url=http://os.archlinuxarm.org/os conf
  [[ ! -d "$dir/root" ]] || return 0
  mkdir -p "$cache/gnupg"
  chmod 700 "$cache" "$cache/gnupg"
  echo ">>> Downloading the Arch Linux ARM image" >&2
  curl -fL --remote-time -z "$cache/$image" -o "$cache/$image" "$url/$image"
  curl -fL -o "$cache/$image.sig" "$url/$image.sig"
  if ! GNUPGHOME="$cache/gnupg" gpg --batch --list-keys "$alarm_key" >/dev/null 2>&1; then
    GNUPGHOME="$cache/gnupg" gpg --batch --keyserver hkps://keyserver.ubuntu.com --recv-keys "$alarm_key"
  fi
  # A good signature by that key, its fingerprint ends the VALIDSIG status line
  if ! GNUPGHOME="$cache/gnupg" gpg --batch --status-fd 1 --verify "$cache/$image.sig" "$cache/$image" 2>/dev/null |
    grep -q "^\[GNUPG:\] VALIDSIG .* $alarm_key\$"; then
    echo "The signature of $cache/$image isn't valid" >&2
    return 1
  fi
  echo ">>> Setting up the Arch Linux ARM root in $dir/root" >&2
  sudo install -d -m 755 "$dir/root" "$dir/pkgcache"
  sudo bsdtar -xpf "$cache/$image" -C "$dir/root"
  # The configuration of the setup, kept next to the root
  conf=$dir/pacman.conf
  alarm_pacman_conf "$dir" | sudo tee "$conf" >/dev/null
  sudo systemd-nspawn -q -D "$dir/root" sh -c 'pacman-key --init && pacman-key --populate archlinuxarm'
  # The marker of mkarchroot, which arch-nspawn checks for
  (
    # shellcheck disable=SC1091 # devtools
    source /usr/share/devtools/lib/archroot.sh
    echo "$CHROOT_VERSION" | sudo tee "$dir/root/.arch-chroot" >/dev/null
  )
  # -s: arch-nspawn would run setarch aarch64 for the CARCH of the image's makepkg.conf, which an
  # x86_64 kernel doesn't know
  sudo arch-nspawn -s -C "$conf" "$dir/root" sh -c \
    'pacman -Rdd --noconfirm linux-aarch64 $(pacman -Qqs "^linux-firmware") && pacman -Syu --noconfirm --needed base-devel'
}

# Prints the pacman.conf of the Arch Linux ARM root in $1/root, with the private repository $2 at $3
# first if given. The mirrors are listed here, as arch-nspawn writes the system's into the mirrorlist,
# and the packages are cached in $1/pkgcache rather than the system's cache.
alarm_pacman_conf() {
  local repo
  cat <<EOF
[options]
Architecture = aarch64
CacheDir = $1/pkgcache
HoldPkg = pacman glibc
SigLevel = Required DatabaseOptional
LocalFileSigLevel = Optional
ParallelDownloads = 5
EOF
  if (($# == 3)); then
    printf '\n[%s]\nSigLevel = Never\nServer = file://%s\n' "$2" "$3"
  fi
  for repo in core extra alarm aur; do
    # shellcheck disable=SC2016 # pacman expands $arch and $repo
    printf '\n[%s]\nServer = http://mirror.archlinuxarm.org/$arch/$repo\n' "$repo"
  done
}

# Prints the makepkg.conf of the native aarch64 builds, the one of the Arch Linux ARM root in $1/root.
# makepkg reads CARCH from it, but arch-nspawn would run setarch for a line starting with CARCH=, which
# an x86_64 kernel doesn't support for aarch64, so it's exported instead.
alarm_makepkg_conf() {
  sed -E 's/^CARCH=/export CARCH=/' "$1/root/etc/makepkg.conf"
  cat <<EOF

# Native aarch64 build under QEMU (./aur-packages build --target aarch64-native)
MAKEFLAGS="-j$(nproc)"
# .NET's W^X double mapping fails under qemu-user
export DOTNET_EnableWriteXorExecute=0
EOF
}

# Prints the makepkg.conf of the cross builds for aarch64 on x86_64: devtools' for x86_64 with the
# CHOST and compiler flags of Arch Linux ARM, from its root in $1/root, which the packages compile
# against (ROOTFS_DIR, as for the cross toolchain of .NET's runtime). makepkg strips the binaries and
# splits off their debug information with binutils for aarch64 (aarch64-linux-gnu-binutils), the
# system's only handle x86_64: as functions for makepkg's own calls, and as OBJCOPY and READELF for
# gdb-add-index, a script of its own, which makepkg runs first to add the GDB index (the system's
# gdb reads aarch64 too). CARCH is exported for arch-nspawn, see alarm_makepkg_conf.
cross_makepkg_conf() {
  grep -v -E '^CARCH=' /usr/share/devtools/makepkg.conf.d/x86_64.conf
  cat <<EOF

# Cross build for aarch64 (./aur-packages build --target aarch64)
export CARCH=aarch64
$(
    # shellcheck disable=SC1091 # Arch Linux ARM's makepkg.conf
    source "$1/root/etc/makepkg.conf"
    declare -p CHOST CFLAGS CXXFLAGS LDFLAGS LTOFLAGS | sed 's/^declare -- //'
  )
export ROOTFS_DIR=$1/root
strip() { aarch64-linux-gnu-strip "\$@"; }
objcopy() { aarch64-linux-gnu-objcopy "\$@"; }
export OBJCOPY=aarch64-linux-gnu-objcopy READELF=aarch64-linux-gnu-readelf
EOF
}

# Succeeds if the packages a package directory builds ($1) are in the repository $2 already, in their
# current version, as makepkg names them with the makepkg.conf $3
build_in_repo() {
  local file found=false
  while IFS= read -r file; do
    # makepkg lists a -debug package whenever debug is on, but only builds one when there are debug
    # symbols, e.g. not for an architecture-independent package
    if [[ ! -f "$2/${file##*/}" ]]; then
      [[ "${file##*/}" == "$(sed -n -E 's/^pkgbase = //p' "$1/.SRCINFO")"-debug-* ]] || return 1
      continue
    fi
    found=true
  done < <(cd "$1" && makepkg --packagelist --config "$3")
  [[ "$found" == true ]]
}

# Prints the makepkg.conf of test builds with the sanitisers $2 (address, undefined or both,
# comma-separated): the makepkg.conf $1 with their flags. Without the checks of undefined that don't work
# for libraries loaded into closed-source programs, like the plugins of game servers (vptr and function
# need the type information of the whole program), or that LLVM's LTO can't build for 32-bit x86
# (pointer-overflow). Executables get the sanitisers' runtime linked in; shared libraries take it from
# the program that loads them, e.g. a server started with the runtime in LD_PRELOAD.
sanitise_makepkg_conf() {
  local flags="-fsanitize=$2 -fno-omit-frame-pointer"
  if [[ ",$2," == *,undefined,* ]]; then
    flags+=" -fno-sanitize=vptr,function,pointer-overflow"
  fi
  cat "$1"
  printf '\n# ./aur-packages build --sanitize=%s: test builds with the sanitisers\n' "$2"
  printf 'CFLAGS+=" %s"\nCXXFLAGS+=" %s"\nLDFLAGS+=" %s"\n' "$flags" "$flags" "$flags"
  # Reports of check() and of the programs the build runs, with where they come from
  printf 'export UBSAN_OPTIONS=print_stacktrace=1\n'
}

# Sets $sysrepo_name, $sysrepo_root and $sysrepo_db to the system's aurutils repository, the one
# aur repo picks: $AUR_REPO, else the only file:// repository of pacman.conf
system_repo() {
  local status
  status=$(aur repo --status) || return
  sysrepo_name=$(sed -n 's/^repo://p' <<<"$status")
  sysrepo_root=$(sed -n 's/^root://p' <<<"$status")
  sysrepo_db=$(sed -n 's/^path://p' <<<"$status")
}

# Succeeds if pacman.conf enables Arch Linux's testing repositories
system_uses_testing() {
  pacman-conf --repo-list | grep -q -x -E '(core|extra|multilib)-testing'
}

# Signs the file $1 with a detached signature ($1.sig), as aur build --sign does: with the key of
# $GPGKEY in the environment, else gpg's default key (default-key in gpg.conf). Not makepkg.conf's
# GPGKEY, which neither aur build nor repo-add read.
sign_package() {
  local -a key=()
  [[ -z "${GPGKEY:-}" ]] || key=(-u "$GPGKEY")
  gpg --detach-sign --no-armor --batch --yes "${key[@]}" --output "$1.sig" -- "$1"
}

# Succeeds if makepkg signs the packages it builds: sign in its BUILDENV, from its configuration as
# makepkg loads it (/etc/makepkg.conf, its .d, the user's own, the environment)
makepkg_signs() {
  (
    # makepkg's library relies on unset variables being empty
    set +u
    # shellcheck disable=SC1091 # makepkg's library
    source /usr/share/makepkg/util.sh
    load_makepkg_config
    [[ " ${BUILDENV[*]} " == *" sign "* ]]
  )
}

# Prints true or false, whether to sign the packages added to the system's aurutils repository
# (system_repo): what --sign or --no-sign ($1 true or false) say, else (auto) if its database is signed
# or makepkg signs the packages it builds
system_repo_signing() {
  if [[ "$1" != auto ]]; then
    printf '%s\n' "$1"
  elif [[ -f "$sysrepo_root/$sysrepo_name.db.sig" ]]; then
    echo "Signing the packages, the database of $sysrepo_name is signed" >&2
    echo true
  elif makepkg_signs; then
    echo "Signing the packages, as makepkg does (sign in BUILDENV)" >&2
    echo true
  else
    echo false
  fi
}

# Fails unless packages can be added to the system's aurutils repository (system_repo), signed or not
# ($1 true or false): its owner can write to it, and a signed database needs signed packages, as with
# aur build. Before the builds, so they aren't for nothing.
system_repo_check() {
  system_repo || return
  if [[ ! -w "$sysrepo_root" ]]; then
    echo "Can't write to $sysrepo_root (the repository $sysrepo_name): run as its owner," \
      "$(stat -c %U "$sysrepo_root")" >&2
    return 1
  fi
  if [[ "$1" == false && -f "$sysrepo_root/$sysrepo_name.db.sig" ]]; then
    echo "The database of $sysrepo_name is signed, the packages need signing too (without --no-sign)" >&2
    return 1
  fi
}

# Adds the package files given to the system's aurutils repository (system_repo), signed with --sign
# ($1 true) like the database. Not pacman's copy of it, as aur build --chroot doesn't: the next pacman -Syu
# syncs it, without a sudo rule for pacsync.
system_repo_add() {
  local signing=$1 file name
  # Not over a newer version, e.g. of an AUR dependency aur sync has updated there since
  local -a added=() repoadd=(--wait-for-lock --prevent-downgrade)
  shift
  system_repo_check "$signing" || return
  if [[ "$signing" == true ]]; then repoadd+=(--sign); fi
  for file; do
    name=${file##*/}
    cp -f -- "$file" "$sysrepo_root/$name"
    if [[ "$signing" == true ]]; then
      sign_package "$sysrepo_root/$name"
    else
      # One of an earlier build of the same file wouldn't match it
      rm -f -- "$sysrepo_root/$name.sig"
    fi
    added+=("$sysrepo_root/$name")
  done
  (cd "$sysrepo_root" && LANG=C repo-add "${repoadd[@]}" -- "$sysrepo_db" "${added[@]}")
  echo "Added ${#added[@]} files to $sysrepo_name ($sysrepo_root), pacman -Syu installs them" >&2
}

# Updates the system's aurutils repository like aur sync -u, but with our packages first: those of
# the top level, local/ and overrides/ that are in the repository and have a newer version here are
# built with their dependencies and added (build --add), then aur sync -u updates the rest, leaving out
# all our packages, which it would replace with the AUR's. Signs the packages of both as build --add
# decides (system_repo_signing), unless --sign or --no-sign says.
cmd_sysupgrade() {
  local signing=auto dir name version
  local -a selected=() names=() ignore=() buildargs=() syncargs=()
  local -A repover=()
  while (($#)); do
    case "$1" in
      --sign | -S) signing=true ;;
      --no-sign) signing=false ;;
      --)
        shift
        break
        ;;
      *)
        echo "Unknown option: $1 (options of aur sync go after --)" >&2
        return 1
        ;;
    esac
    shift
  done
  require sysupgrade aur:aurutils
  system_repo
  signing=$(system_repo_signing "$signing")
  while IFS=$'\t' read -r name version; do
    repover[$name]=$version
  done < <(aur repo --database "$sysrepo_name" --list)
  while IFS= read -r dir; do
    mapfile -t names < <(build_pkgnames "$dir")
    ignore+=("${names[@]}")
    version=$(srcinfo_text_version <"$dir/.SRCINFO")
    for name in "${names[@]}"; do
      if [[ -n "${repover[$name]-}" ]] && (($(vercmp "$version" "${repover[$name]}") > 0)); then
        echo "$dir: ${repover[$name]} -> $version" >&2
        selected+=("$dir")
        break
      fi
    done
  done < <(package_dirs)
  if [[ "$signing" == true ]]; then
    buildargs+=(--sign)
    syncargs+=(--sign)
  else
    buildargs+=(--no-sign)
  fi
  if ((${#selected[@]})); then
    # In a subshell, as its traps outlive it
    (cmd_build --add "${buildargs[@]}" -- "${selected[@]}")
  else
    echo "Our packages in $sysrepo_name are up to date" >&2
  fi
  aur sync --database "$sysrepo_name" --upgrades --ignore "$(
    IFS=,
    printf '%s' "${ignore[*]}"
  )" "${syncargs[@]}" "$@"
}

cmd_build() {
  local method=chroot install=false dryrun=false keep=false dotnetbin=false libsbin=false testing=false
  local target='' native=false cross=false reuse='' sanitise='' sanitiser add=false signing=auto
  local arg pkg name file dir repo='' conf='' reponame=aur-build
  local makepkgconf=/usr/share/devtools/makepkg.conf.d/x86_64.conf
  local crossrepo='' crossconf='' crossmakepkg='' crossname=aur-build-aarch64
  # The containers, apart from the ones of aurutils (/var/lib/aurbuild), which builds the system's
  # packages with its own configuration
  local chrootbase=${AUR_BUILD_CHROOT:-/var/lib/aur-packages-chroot}
  local chrootdir=$chrootbase/x86_64 alarmdir=$chrootbase/aarch64 crossdir=$chrootbase/x86_64-cross-aarch64
  local multilibdir=$chrootbase/multilib-x86_64 pkgconf
  local -a roots=() order=() expand cmd preinstall=() files arches names chrootargs=() crossargs=() pkgargs
  local ver
  local -A built=()
  # The private repository's files, the packages and the copies --add puts into the system's repository
  # are read by pacman's DownloadUser (alpm) in the chroots, and by pacman, whatever the umask of the
  # user building (027 for a dedicated aurutils user, say)
  umask 022
  while (($#)); do
    case "$1" in
      --chroot) method=chroot ;;
      --local) method=local ;;
      --install) install=true ;;
      --dry-run | -n) dryrun=true ;;
      --keep) keep=true ;;
      --add) add=true ;;
      --sign) signing=true ;;
      --no-sign) signing=false ;;
      --dotnet-bin) dotnetbin=true ;;
      --libs-bin) libsbin=true ;;
      --testing) testing=true ;;
      --sanitize)
        shift
        sanitise=${1:-}
        ;;
      --sanitize=*) sanitise=${1#*=} ;;
      --target)
        shift
        target=${1:-}
        ;;
      --target=*) target=${1#*=} ;;
      --repo)
        shift
        reuse=${1:-}
        ;;
      --repo=*) reuse=${1#*=} ;;
      --)
        shift
        break
        ;;
      -*)
        echo "Unknown option: $1" >&2
        return 1
        ;;
      *) break ;;
    esac
    shift
  done
  if (($# == 0)); then
    echo "Usage: aur-packages build [--chroot|--local] [--install] [--dry-run] [--keep] [--add [--sign|--no-sign]] [--repo DIR]" \
      "[--dotnet-bin]" \
      "[--libs-bin] [--testing] [--sanitize undefined|address|address,undefined] [--target aarch64|aarch64-native]" \
      "<template|package>..." >&2
    return 1
  fi
  case "$target" in
    '') ;;
    aarch64) cross=true ;;
    aarch64-native) native=true ;;
    *)
      echo "Unknown target: $target (aarch64 cross-builds, aarch64-native builds under QEMU)" >&2
      return 1
      ;;
  esac
  if [[ "$method" == local && ("$dotnetbin" == true || "$libsbin" == true || "$testing" == true || -n "$target" ||
    -n "$reuse") ]]; then
    echo "--dotnet-bin, --libs-bin, --testing, --target and --repo need a chroot build, a local one uses what's installed" >&2
    return 1
  fi
  # What the build needs, before it changes anything (--target sets up the Arch Linux ARM root first),
  # even for --dry-run, so the plan it prints can run
  local -a tools=(makepkg:pacman)
  if [[ "$method" == chroot ]]; then
    tools+=(aur:aurutils makechrootpkg:devtools arch-nspawn:devtools)
  fi
  if [[ "$add" == true ]]; then
    tools+=(aur:aurutils repo-add:pacman gpg:gnupg)
  fi
  if [[ -n "$target" ]]; then
    tools+=(curl:curl gpg:gnupg)
  fi
  require build "${tools[@]}"
  # Programs for aarch64 run in the Arch Linux ARM root under QEMU, registered with binfmt_misc
  if [[ -n "$target" && ! -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ]]; then
    echo "--target needs QEMU for aarch64 programs: qemu-user-static-binfmt, then" \
      "systemctl restart systemd-binfmt" >&2
    return 1
  fi
  if [[ -n "$sanitise" ]]; then
    local -a sanitisers
    IFS=, read -ra sanitisers <<<"$sanitise"
    for sanitiser in "${sanitisers[@]}"; do
      if [[ "$sanitiser" != address && "$sanitiser" != undefined ]]; then
        echo "Unknown sanitiser: $sanitiser (address, undefined or both, comma-separated)" >&2
        return 1
      fi
    done
    if [[ "$method" == local || -n "$target" ]]; then
      echo "--sanitize needs a chroot build for x86_64" >&2
      return 1
    fi
    # The test builds are no use without their packages
    keep=true
  fi
  # Into the system's aurutils repository: x86_64 packages, built against the repositories the system
  # uses, as a package built against stable can depend on a library soname testing has replaced
  if [[ "$signing" != auto && "$add" == false ]]; then
    echo "--sign and --no-sign are for the packages --add adds" >&2
    return 1
  fi
  if [[ "$add" == true ]]; then
    if [[ "$method" == local || -n "$sanitise" || -n "$target" ]]; then
      echo "--add needs a chroot build for x86_64, without --sanitize (test builds aren't to be installed)" >&2
      return 1
    fi
    system_repo
    signing=$(system_repo_signing "$signing")
    if [[ "$dryrun" == false ]]; then system_repo_check "$signing"; fi
    if system_uses_testing; then
      if [[ "$testing" == false ]]; then
        echo "The system uses the testing repositories, building against them (--testing)" >&2
        testing=true
      fi
    elif [[ "$testing" == true ]]; then
      echo "--testing builds against the testing repositories, which the system doesn't use" >&2
      return 1
    fi
  fi
  if [[ "$testing" == true && -n "$target" ]]; then
    echo "--testing is for Arch Linux's testing repositories, Arch Linux ARM has none" >&2
    return 1
  fi
  # devtools' configurations of the chroots, the testing ones with --testing. Those have chroots of
  # their own, as a chroot upgraded to the testing repositories can't go back.
  local devtoolsconf=extra multilibconf=multilib
  if [[ "$testing" == true ]]; then
    devtoolsconf=extra-testing multilibconf=multilib-testing
    chrootdir=$chrootbase/x86_64-testing multilibdir=$chrootbase/multilib-x86_64-testing
  fi
  if [[ -n "$target" && "$(uname -m)" != x86_64 ]]; then
    echo "--target is for x86_64 hosts, build natively on $(uname -m)" >&2
    return 1
  fi
  if [[ "$native" == true && "$dotnetbin" == false ]]; then
    echo "Arch Linux ARM has no .NET, --target aarch64-native builds with Microsoft's (--dotnet-bin)" >&2
    dotnetbin=true
  fi

  # The -bin variants of the selector packages, preinstalled into each chroot (makechrootpkg -I) with
  # what they depend on, so pacman doesn't resolve the names the packages depend on to Arch's .NET
  # (dotnet-sdk-10.0) or the source-built selectors in another repository instead. The ASP.NET ones
  # are for powershell's checkdepends.
  local -a dotnetbinpkgs=()
  if [[ "$dotnetbin" == true ]]; then
    # One per .NET version, e.g. dotnet-build-deps-10.0-bin for dotnet-build-deps-10.0, with Microsoft's
    # packages of that version (dotnet-core-10.0-bin: dotnet-sdk-10.0-bin, …). Not the ones without a
    # source-built variant (dotnet-build-deps-11.0-bin), which are the only provider anyway, and whose
    # prerelease of .NET doesn't belong in the chroots of the others.
    for name in dotnet-build-deps-*-bin; do
      [[ -d "${name%-bin}" ]] || continue
      build_alias["${name%-bin}"]=$name
      ver=${name#dotnet-build-deps-}
      ver=${ver%-bin}
      dotnetbinpkgs+=("dotnet-host-$ver-bin" "dotnet-runtime-$ver-bin" "dotnet-targeting-pack-$ver-bin"
        "dotnet-sdk-$ver-bin" "aspnet-runtime-$ver-bin" "aspnet-targeting-pack-$ver-bin")
      preinstall+=("${dotnetbinpkgs[@]: -6}" "$name")
    done
  fi
  # powershell-build-deps and powershell-editor-services-build-deps resolve to the packages of the split
  # powershell-build-deps-bin, which are all preinstalled
  if [[ "$libsbin" == true ]]; then
    mapfile -t names < <(build_pkgnames powershell-build-deps-bin)
    for name in "${names[@]}"; do
      build_alias[${name%-bin}]=powershell-build-deps-bin
    done
    preinstall+=("${names[@]}")
  fi

  # Each argument is a template, expanded to its root packages, or a package directory itself
  for arg in "$@"; do
    arg=${arg%/}
    mapfile -t expand < <(build_template "$arg")
    if ((${#expand[@]})); then
      roots+=("${expand[@]}")
    elif dir=$(package_dir "$arg"); then
      roots+=("$dir")
    else
      echo "Not a template or package: $arg" >&2
      return 1
    fi
  done

  mapfile -t order < <(build_order "${roots[@]}")
  if ((${#order[@]} == 0)); then
    echo "Nothing to build" >&2
    return 1
  fi

  # Clean-chroot builds go into a private repository, so they don't touch the system's aurutils
  # repository; each build resolves the packages built before it from there. --repo continues in one
  # kept before, skipping the packages that are in there already.
  if [[ "$method" == chroot && "$dryrun" == true ]]; then
    repo=${reuse:-<repo>}
    conf=$repo/pacman.conf
  elif [[ "$method" == chroot ]]; then
    if [[ "$native" == true || "$cross" == true ]]; then
      alarm_root "$alarmdir"
    fi
    if [[ -n "$reuse" ]]; then
      repo=$(cd "$cwd" && realpath "$reuse")
      conf=$repo/pacman.conf
      keep=true
      if [[ ! -f "$conf" ]]; then
        echo "$repo isn't a repository of ./aur-packages build --keep" >&2
        return 1
      fi
    else
      repo=$(mktemp -d --tmpdir aur-build.XXXXXX)
      # Readable by the download user of pacman in the chroot (DownloadUser = alpm)
      chmod 755 "$repo"
      conf=$repo/pacman.conf
      if [[ "$keep" == false ]]; then
        # shellcheck disable=SC2064 # expand $repo now, when the trap is set, not when it runs
        trap "rm -rf '$repo'" RETURN
      fi
      if [[ "$native" == true ]]; then
        alarm_pacman_conf "$alarmdir" "$reponame" "$repo" >"$conf"
      else
        # The pacman.conf of clean-chroot builds (devtools, as pkgctl build uses it) with the private
        # repository. Not the system's, whose testing repositories, the aurutils repo or mirrorlists
        # elsewhere don't belong in a clean chroot.
        devtools_pacman_conf "$devtoolsconf.conf" "$reponame" "$repo" >"$conf"
      fi
      # An empty database, so the first build can sync the repository before it has any packages
      tar -czf "$repo/$reponame.db.tar.gz" -T /dev/null
      ln -sf "$reponame.db.tar.gz" "$repo/$reponame.db"
    fi
  fi

  # A native aarch64 build runs everything in the Arch Linux ARM root, under QEMU
  if [[ "$native" == true ]]; then
    chrootdir=$alarmdir
    makepkgconf=$repo/makepkg-aarch64.conf
    if [[ "$dryrun" == false ]]; then alarm_makepkg_conf "$alarmdir" >"$makepkgconf"; fi
    chrootargs+=(--makepkg-conf "$makepkgconf")
  fi
  chrootargs+=(--directory "$chrootdir")
  # Test builds with the sanitisers take their flags from a makepkg.conf of their own, in the normal and
  # the multilib container
  local -a sanitiseargs=()
  if [[ -n "$sanitise" ]]; then
    sanitiseargs=(--makepkg-conf "$repo/makepkg-sanitise.conf")
    if [[ "$dryrun" == false ]]; then
      sanitise_makepkg_conf "$makepkgconf" "$sanitise" >"$repo/makepkg-sanitise.conf"
    fi
    chrootargs+=("${sanitiseargs[@]}")
  fi

  # A cross build builds everything for x86_64 as usual, those for aarch64 as well afterwards, in a
  # container of their own with the cross toolchain and the Arch Linux ARM root they compile against.
  # They go into a repository of their own, listed last, so the x86_64 ones they depend on come from
  # the private repository.
  if [[ "$cross" == true ]]; then
    crossrepo=$repo/aarch64
    crossconf=$repo/pacman-cross-aarch64.conf
    crossmakepkg=$repo/makepkg-cross-aarch64.conf
    # base-devel and the cross toolchain (also the Rust standard library for aarch64), comma-separated
    # for aur build
    local crossbase=base-devel,clang,lld,aarch64-linux-gnu-binutils,rust-aarch64-gnu
    crossargs=(--directory "$crossdir" --makepkg-conf "$crossmakepkg" --bind "$alarmdir/root"
      --base-packages "$crossbase")
    if [[ "$dryrun" == false ]]; then
      mkdir -p "$crossrepo"
      chmod 755 "$crossrepo"
      if [[ ! -f "$crossrepo/$crossname.db.tar.gz" ]]; then
        tar -czf "$crossrepo/$crossname.db.tar.gz" -T /dev/null
        ln -sf "$crossname.db.tar.gz" "$crossrepo/$crossname.db"
      fi
      {
        cat "$conf"
        printf '\n[%s]\nSigLevel = Never\nServer = file://%s\n' "$crossname" "$crossrepo"
      } >"$crossconf"
      cross_makepkg_conf "$alarmdir" >"$crossmakepkg"
    fi
  fi

  # Dependencies only the AUR has, built by aurutils into the private repository first (it builds
  # their own AUR dependencies as well): e.g. lasso for sogo, or Microsoft's .NET, the SDK each -bin
  # selector in the build order depends on, dotnet-sdk-10.0-bin (dotnet-core-10.0-bin) for
  # dotnet-build-deps-10.0-bin with --dotnet-bin. A .NET only Microsoft builds, e.g. a prerelease
  # (dotnet-build-deps-11.0-bin, dotnet-sdk-preview-bin), has no other selector, so it's always used.
  # Names that aren't packages in the AUR are provides of the ones built, e.g. dotnet-runtime-11.0
  # of dotnet-runtime-bin, which dotnet-sdk-bin brings along.
  if [[ "$method" == chroot ]]; then
    local -a aurdeps=() aurnames=()
    mapfile -t aurdeps < <(aur_only_deps "/usr/share/devtools/pacman.conf.d/$multilibconf.conf" "${order[@]}")
    if ((${#aurdeps[@]})); then
      mapfile -t aurnames < <(aur query -t info "${aurdeps[@]}" | jq -r '.results[].Name' | sort)
    fi
    for name in "${aurnames[@]}"; do
      cmd=(aur sync --chroot --no-sync --database "$reponame" --root "$repo" --pacman-conf "$conf"
        "${chrootargs[@]}" --no-view --noconfirm "$name")
      if [[ "$dryrun" == true ]]; then
        printf '%s\n' "${cmd[*]}"
      elif compgen -G "$repo/$name-[0-9]*.pkg.tar.zst" >/dev/null; then
        echo ">>> $name is in $repo already" >&2
      else
        echo ">>> Building $name (aur sync)" >&2
        # aur sync exits with 22 when the dependencies have a cycle, which checkdepends can make,
        # e.g. python-celery's on python-pytest-celery, which depends on it: then they're built
        # without their checkdepends and check(), as aur sync suggests. Any other failure stops.
        local status=0
        "${cmd[@]}" || status=$?
        if ((status == 22)); then
          echo ">>> $name: its dependencies have a cycle, building them without check()" >&2
          "${cmd[@]}" --no-check
        elif ((status)); then
          return "$status"
        fi
      fi
    done
    for name in "${aurdeps[@]}"; do
      [[ " ${aurnames[*]} " != *" $name "* ]] || continue
      if [[ "$dryrun" == true ]]; then
        echo "# $name: provided by the AUR packages above" >&2
      elif ! repo_provides "$repo" "$name"; then
        echo "${0##*/}: $name is neither in the repositories, nor a package of this repository or the AUR, nor provided by one" >&2
        return 1
      fi
    done
  fi
  for name in "${dotnetbinpkgs[@]}"; do
    built[$name]=1
  done

  for pkg in "${order[@]}"; do
    mapfile -t arches < <(build_arches "$pkg")
    if [[ "$native" == true && " ${arches[*]} " != *" aarch64 "* && " ${arches[*]} " != *" any "* ]]; then
      echo ">>> Skipping $pkg, it isn't for aarch64" >&2
      continue
    fi
    if [[ "$method" == chroot ]]; then
      pkgconf=$conf
      pkgargs=("${chrootargs[@]}")
      # A package against multilib builds in a multilib container, with the same private repository
      if [[ "$native" == false ]] && build_multilib "$pkg"; then
        pkgconf=$repo/pacman-multilib.conf
        pkgargs=(--directory "$multilibdir" --base-packages "base-devel,multilib-devel" "${sanitiseargs[@]}")
        if [[ "$dryrun" == false && ! -f "$pkgconf" ]]; then
          devtools_pacman_conf "$multilibconf.conf" "$reponame" "$repo" >"$pkgconf"
        fi
      fi
      cmd=(aur build --chroot --no-sync --database "$reponame" --root "$repo" --pacman-conf "$pkgconf" "${pkgargs[@]}"
        --force)
      # The packages to preinstall that are built by now
      files=()
      for name in "${preinstall[@]}"; do
        [[ -n "${built[$name]:-}" ]] || continue
        if [[ "$dryrun" == true ]]; then
          files+=("$repo/$name-<version>.pkg.tar.zst")
          continue
        fi
        for file in "$repo/$name"-[0-9]*.pkg.tar.zst; do
          if [[ -f "$file" ]]; then files+=("$file"); fi
        done
      done
      if ((${#files[@]})); then
        files=("--cargs=$(printf -- '-I,%s,' "${files[@]}")")
        files[0]=${files[0]%,}
      fi
      cmd+=("${files[@]}")
    else
      cmd=(makepkg --force --cleanbuild --nodeps)
      if [[ "$install" == true ]]; then cmd+=(--install); fi
    fi
    if [[ "$dryrun" == true ]]; then
      printf '(cd %s && %s)\n' "$pkg" "${cmd[*]}"
    elif [[ -n "$reuse" ]] && build_in_repo "$pkg" "$repo" "$makepkgconf"; then
      echo ">>> $pkg is in $repo already" >&2
    else
      echo ">>> Building $pkg" >&2
      (cd "$pkg" && "${cmd[@]}")
    fi
    # By the names of its packages, which the packages to preinstall are looked up by
    mapfile -t names < <(build_pkgnames "$pkg")
    for name in "${names[@]}"; do
      built[$name]=1
    done

    if [[ "$cross" == true && " ${arches[*]} " == *" aarch64 "* ]]; then
      cmd=(aur build --chroot --no-sync --database "$crossname" --root "$crossrepo" --pacman-conf "$crossconf"
        "${crossargs[@]}" --force "${files[@]}")
      if [[ "$dryrun" == true ]]; then
        printf '(cd %s && %s)\n' "$pkg" "${cmd[*]}"
      elif [[ -n "$reuse" ]] && build_in_repo "$pkg" "$crossrepo" "$crossmakepkg"; then
        echo ">>> $pkg for aarch64 is in $crossrepo already" >&2
      else
        echo ">>> Building $pkg for aarch64" >&2
        (cd "$pkg" && "${cmd[@]}")
      fi
    fi
  done

  if [[ "$add" == true ]]; then
    if [[ "$dryrun" == true ]]; then
      echo "# then add $repo/*.pkg.tar.zst to the system's aurutils repository$([[ "$signing" == false ]] || echo ", signed")" >&2
    else
      # Only once all have been built, so a failed build leaves the repository as it was
      system_repo_add "$signing" "$repo"/*.pkg.tar.zst
    fi
  fi

  if [[ "$method" == chroot && "$keep" == true && "$dryrun" == false ]]; then
    echo "Repository kept at $repo" >&2
    if [[ -n "$sanitise" ]]; then
      echo "Its packages are test builds with -fsanitize=$sanitise, not to be installed as the usual ones" >&2
    fi
    if [[ "$cross" == true ]]; then echo "The aarch64 packages are in $crossrepo" >&2; fi
  fi
}

# Prints the upstream commit a package's current pkgver was published from, best effort, empty if it
# can't be determined. Option B: the <repository commit> of the published NuGet nuspec, found from
# the package's NuGet id (_nugetid, else the first of _packages, else the .nvchecker.toml packageid).
# A PKGBUILD may define a _commit_lookup function to override this (e.g. VMR packages not on NuGet).
resolve_commit() {
  (
    local id ver lid base out tmp
    # shellcheck disable=SC1090,SC1091 # the package's PKGBUILD, sourced like makepkg reads it
    source "$1/PKGBUILD" >/dev/null 2>&1 || exit 1
    if declare -F _commit_lookup >/dev/null; then
      _commit_lookup
      exit
    fi
    id=${_nugetid:-}
    if [[ -z "$id" && -n "${_packages+x}" && ${#_packages[@]} -gt 0 ]]; then id=${_packages[0]}; fi
    if [[ -z "$id" && -f "$1/.nvchecker.toml" ]]; then
      id=$(sed -n -E 's/.*packageid:([^&"]+).*/\1/p' "$1/.nvchecker.toml" | head -1)
    fi
    [[ -n "$id" ]] || exit 1
    ver=$pkgver
    lid=${id,,}
    base="https://api.nuget.org/v3-flatcontainer/$lid/$ver"
    # The flat container serves the nuspec on its own; fall back to the whole package if it doesn't
    out=$(curl -fsSL "$base/$lid.nuspec" 2>/dev/null) || out=''
    if [[ -z "$out" ]]; then
      tmp=$(mktemp) || exit 1
      if curl -fsSL "$base/$lid.$ver.nupkg" -o "$tmp" 2>/dev/null; then
        out=$(bsdtar -xOf "$tmp" '*.nuspec' 2>/dev/null)
      fi
      rm -f "$tmp"
    fi
    printf '%s' "$out" | grep -oiE 'commit="[0-9a-f]{40}"' | grep -oiE '[0-9a-f]{40}' | head -1
  )
}

# Prints the values a package's pinned variables should have, "NAME VALUE" a line, nothing for a
# package without pins: the PKGBUILD's _pins_lookup for several (run in the package's folder, e.g.
# the commits of a tag's submodules, or of branches and the version from them), else the _commit of
# resolve_commit. A value is empty if it can't be determined.
resolve_pins() {
  (
    local github_token
    github_token=$(github_token)
    # The lookups' requests (resolve_commit's and the PKGBUILDs' _pins_lookup) give up on a stalled
    # connection and try again, instead of waiting for it forever: no timeout on the whole transfer,
    # as some download a whole package. Those to GitHub's API go with the token of github_token, so
    # they get its rate limit rather than the 60 requests an hour without one, which the update check
    # uses up: a lookup that hits it leaves its pin unresolved. On stdin rather than the command line,
    # where other users could read it.
    curl() {
      local arg
      local -a stall=(--connect-timeout 15 --speed-limit 1024 --speed-time 30 --retry 2)
      if [[ -n "$github_token" ]]; then
        for arg; do
          if [[ "$arg" == https://api.github.com/* ]]; then
            command curl "${stall[@]}" -K - "$@" <<<"header = \"Authorization: Bearer $github_token\""
            return
          fi
        done
      fi
      command curl "${stall[@]}" "$@"
    }
    cd "$1" || exit 1
    # shellcheck disable=SC1091 # the package's PKGBUILD, sourced like makepkg reads it
    source ./PKGBUILD >/dev/null 2>&1 || exit 1
    if declare -F _pins_lookup >/dev/null; then
      _pins_lookup
      exit
    fi
    [[ "${_commit-}" =~ ^[0-9a-f]{7,40}$ ]] || exit 0
    echo "_commit $(resolve_commit .)"
  )
}

# The value of a pinned variable in a PKGBUILD: pin_value <package> <name>
pin_value() {
  sed -n -E "s/^$2=[\"']?([^\"']*)[\"']?\$/\1/p" "$1/PKGBUILD" | head -1
}

# Sets a pinned variable in a PKGBUILD, and pkgrel to 1 with pkgver: set_pin <package> <name> <value>
set_pin() {
  sed -i -E "s/^($2=[\"']?)[^\"']*([\"']?)\$/\1$3\2/" "$1/PKGBUILD"
  if [[ "$2" == pkgver ]]; then sed -i 's/^pkgrel=.*/pkgrel=1/' "$1/PKGBUILD"; fi
}

# Commits in full are shown as 12 characters
short_pin() {
  if [[ "$1" =~ ^[0-9a-f]{40}$ ]]; then echo "${1:0:12}"; else echo "$1"; fi
}

# updpkgsums on a package whose pins changed. An interrupted download leaves a .part file behind,
# which makepkg resumes with a range request (curl -C -). GitHub's archives of a commit
# (archive/<commit>.tar.gz) are made on the fly and don't support ranges, so curl fails (33) on every
# later try until the file is gone: remove them first, at the cost of starting a resumable download
# again.
update_checksums() {
  find "$1" -maxdepth 1 -name '*.part' -type f -delete
  (cd "$1" && updpkgsums)
}

cmd_commits() {
  local update=false pkg pin name cur new changed ok
  local -a selected pins
  require commits curl:curl jq:jq
  if [[ "${1-}" == --update ]]; then
    update=true
    shift
  fi
  select_packages "$@"
  for pkg in "${selected[@]}"; do
    pins=()
    mapfile -t pins < <(resolve_pins "$pkg")
    # Only packages that pin something
    ((${#pins[@]})) || continue
    changed=false ok=0
    for pin in "${pins[@]}"; do
      name=${pin%% *} new=${pin#"$name"}
      new=${new# }
      cur=$(pin_value "$pkg" "$name")
      if [[ -z "$new" || "$new" == null ]]; then
        printf '%-38s %s unresolved (current %s)\n' "$pkg" "$name" "$(short_pin "$cur")"
      elif [[ "$new" == "$cur" ]]; then
        ok=$((ok + 1))
      elif [[ "$update" == true ]]; then
        set_pin "$pkg" "$name" "$new"
        changed=true
        printf '%-38s %s updated %s -> %s\n' "$pkg" "$name" "$(short_pin "$cur")" "$(short_pin "$new")"
      else
        printf '%-38s %s STALE %s -> %s\n' "$pkg" "$name" "$(short_pin "$cur")" "$(short_pin "$new")"
      fi
    done
    if ((ok == ${#pins[@]})); then
      if ((ok == 1)); then
        printf '%-38s ok %s %s\n' "$pkg" "${pins[0]%% *}" "$(short_pin "${pins[0]#* }")"
      else
        printf '%-38s ok, %d pins\n' "$pkg" "$ok"
      fi
    fi
    if [[ "$changed" == true ]]; then
      update_checksums "$pkg"
      shfmt --write "$pkg/PKGBUILD"
      (cd "$pkg" && makepkg --printsrcinfo >.SRCINFO)
    fi
  done
}

command=${1-help}
(($#)) && shift
case "$command" in
  updates | upgrade | tray | build | sysupgrade | commits)
    "cmd_$command" "$@"
    ;;
  *)
    echo "aur-packages.sh: $command isn't a command of the bash part, run ./aur-packages" >&2
    exit 2
    ;;
esac
