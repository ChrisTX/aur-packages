#!/usr/bin/env bats
# _check_prebuilt, which the .NET packages' package() run so that no prebuilt binary from nuget.org
# slips in instead of one built from source: a check that fails silently if it breaks, as the build
# passes either way. Each case runs against every PKGBUILD's copy of it, so a copy that drifts in what
# it detects fails as well.

# The copies that let the packages of the -bin selectors through (pacman -T, see CONTRIBUTING.md), and
# those that leave .NET's own packs (DotnetPlatform) out, which powershell copies into $PSHOME/ref
SELECTORS=(powershell powershell-lts powershell-preview powershell-editor-services)
PLATFORM=(powershell powershell-lts powershell-preview)

setup_file() {
  cd "$BATS_TEST_DIRNAME/../.." || exit
  local pkgbuild
  COPIES=()
  for pkgbuild in */PKGBUILD local/*/PKGBUILD overrides/*/PKGBUILD; do
    grep -q '^_check_prebuilt() *{' "$pkgbuild" && COPIES+=("${pkgbuild%/PKGBUILD}")
  done
  export COPIES_LIST="${COPIES[*]}"
}

setup() {
  read -ra COPIES <<<"$COPIES_LIST"
  ROOT="$BATS_TEST_DIRNAME/../.."
  # pacman -T and uname -m as each case needs: the selectors in $INSTALLED, the host in $MACHINE
  mkdir -p "$BATS_TEST_TMPDIR/bin"
  cat >"$BATS_TEST_TMPDIR/bin/pacman" <<'EOF'
#!/bin/bash
[[ $1 == -T ]] || exit 1
[[ " $INSTALLED " == *" $2 "* ]] || { echo "$2"; exit 127; }
EOF
  cat >"$BATS_TEST_TMPDIR/bin/uname" <<'EOF'
#!/bin/bash
echo "$MACHINE"
EOF
  chmod +x "$BATS_TEST_TMPDIR/bin/"*
  PATH="$BATS_TEST_TMPDIR/bin:$PATH"
  export INSTALLED="" MACHINE=x86_64 CARCH=x86_64 _dotnetsdkver=10.0
}

# A restored NuGet package in $srcdir/nuget: its feed (a URL or a local folder), its binary, and the
# type or repository of its .nuspec
restored() {
  local name=$1 source=$2 binary=$3 nuspec=${4:-}
  local folder="$srcdir/nuget/$name/1.0.0"
  mkdir -p "$folder/lib/net10.0"
  printf '{"version": 2, "contentHash": "x", "source": "%s"}\n' "$source" >"$folder/.nupkg.metadata"
  printf '<package><metadata>%s</metadata></package>\n' "$nuspec" >"$folder/$name.nuspec"
  printf '%s' "$name" >"$folder/lib/net10.0/$binary"
}

# The binary of a restored package, shipped in $pkgdir
shipped() {
  mkdir -p "$pkgdir/usr/lib/app"
  cp "$srcdir/nuget/$1/1.0.0/lib/net10.0/$2" "$pkgdir/usr/lib/app/$2"
}

# Runs _check_prebuilt of each copy in the given list on a case, prepared by the function given, in
# a fresh $srcdir and $pkgdir; expects it to fail (1) or pass (0), with a message naming the binary
fixture() {
  local expect=$1 prepare=$2 copy failures=()
  shift 2
  for copy in "$@"; do
    srcdir="$BATS_TEST_TMPDIR/$copy/src" pkgdir="$BATS_TEST_TMPDIR/$copy/pkg"
    rm -rf "${srcdir%/src}"
    mkdir -p "$srcdir" "$pkgdir"
    "$prepare"
    # shellcheck disable=SC1090
    source <(awk '/^_check_prebuilt\(\) *\{/ {p=1} p {print} p && /^}/ {exit}' "$ROOT/$copy/PKGBUILD")
    local status=0 output
    output=$(_check_prebuilt "$srcdir/nuget" 2>&1) || status=$?
    if [[ $status != "$expect" ]]; then
      failures+=("$copy: status $status, expected $expect: $output")
    elif [[ $expect == 1 && $output != *"Prebuilt binary: "* ]]; then
      failures+=("$copy: no message naming the binary: $output")
    fi
    [[ -d $srcdir/check-prebuilt ]] && failures+=("$copy: left $srcdir/check-prebuilt behind")
  done
  if ((${#failures[@]})); then
    printf '%s\n' "${failures[@]}" >&2
    return 1
  fi
}

# All copies except those given, in OTHERS
others() {
  local copy skip
  OTHERS=()
  for copy in "${COPIES[@]}"; do
    for skip in "$@"; do [[ $copy == "$skip" ]] && continue 2; done
    OTHERS+=("$copy")
  done
}

NUGET=https://api.nuget.org/v3/index.json
VMR='<repository type="git" url="https://github.com/dotnet/dotnet" />'
PACK='<packageTypes><packageType name="DotnetPlatform" /></packageTypes>'

@test "the copies are all found, and the groups are copies" {
  ((${#COPIES[@]} >= 29))
  local copy
  for copy in "${SELECTORS[@]}" "${PLATFORM[@]}"; do
    [[ " ${COPIES[*]} " == *" $copy "* ]] || {
      echo "$copy has no _check_prebuilt" >&2
      return 1
    }
  done
}

own_build() {
  restored Lib "$NUGET" Lib.dll
  mkdir -p "$pkgdir/usr/lib/app"
  printf 'built from source' >"$pkgdir/usr/lib/app/Lib.dll"
}
@test "a binary built from source passes" {
  fixture 0 own_build "${COPIES[@]}"
}

prebuilt_dll() {
  restored Lib "$NUGET" Lib.dll
  shipped Lib Lib.dll
}
@test "a binary from nuget.org fails" {
  fixture 1 prebuilt_dll "${COPIES[@]}"
}

prebuilt_so() {
  restored Native "$NUGET" libnative.so.1
  shipped Native libnative.so.1
}
@test "a versioned shared library from nuget.org fails" {
  fixture 1 prebuilt_so "${COPIES[@]}"
}

local_feed() {
  restored Lib /usr/share/nuget/packages Lib.dll
  shipped Lib Lib.dll
}
@test "a binary from a local feed passes" {
  fixture 0 local_feed "${COPIES[@]}"
}

not_a_binary() {
  restored Lib "$NUGET" Lib.xml
  shipped Lib Lib.xml
}
@test "a file that isn't a binary passes" {
  fixture 0 not_a_binary "${COPIES[@]}"
}

inside_nupkg() {
  restored Lib "$NUGET" Lib.dll
  local package="$BATS_TEST_TMPDIR/nupkg"
  rm -rf "$package"
  mkdir -p "$package/lib/net10.0" "$pkgdir/usr/share/nuget/packages"
  cp "$srcdir/nuget/Lib/1.0.0/lib/net10.0/Lib.dll" "$package/lib/net10.0/"
  bsdtar --format zip -cf "$pkgdir/usr/share/nuget/packages/ours.1.0.0.nupkg" -C "$package" .
}
@test "a binary from nuget.org inside a shipped .nupkg fails" {
  fixture 1 inside_nupkg "${COPIES[@]}"
}

vmr_package() {
  restored Microsoft.Vmr "$NUGET" Vmr.dll "$VMR"
  shipped Microsoft.Vmr Vmr.dll
}
@test "a package of .NET's VMR from nuget.org fails without the -bin selector" {
  fixture 1 vmr_package "${COPIES[@]}"
}

@test "a package of .NET's VMR from nuget.org passes with dotnet-build-deps-bin" {
  INSTALLED="dotnet-build-deps-10.0-bin"
  fixture 0 vmr_package "${SELECTORS[@]}"
  others "${SELECTORS[@]}"
  fixture 1 vmr_package "${OTHERS[@]}"
}

@test "a package of .NET's VMR from nuget.org passes in a cross build" {
  CARCH=aarch64
  fixture 0 vmr_package "${SELECTORS[@]}"
  others "${SELECTORS[@]}"
  fixture 1 vmr_package "${OTHERS[@]}"
}

@test "a library from nuget.org passes with the build-deps -bin selector, not with .NET's" {
  INSTALLED="powershell-build-deps-bin powershell-editor-services-build-deps-bin"
  fixture 0 prebuilt_dll "${SELECTORS[@]}"
  others "${SELECTORS[@]}"
  fixture 1 prebuilt_dll "${OTHERS[@]}"
  INSTALLED="dotnet-build-deps-10.0-bin"
  fixture 1 prebuilt_dll "${COPIES[@]}"
}

platform_pack() {
  restored Microsoft.NETCore.App.Runtime "$NUGET" System.Runtime.dll "$PACK"
  shipped Microsoft.NETCore.App.Runtime System.Runtime.dll
}
@test "a pack of .NET itself passes only where powershell copies from it" {
  fixture 0 platform_pack "${PLATFORM[@]}"
  others "${PLATFORM[@]}"
  fixture 1 platform_pack "${OTHERS[@]}"
}
