# Completion of aur-packages for bash, in ~/.bashrc: source <(aur-packages completion bash)
# bash takes it for ./aur-packages as well, by the name after the last slash. The candidates come from
# the program itself (aur-packages __complete), so they always match the checkout's commands.
# shellcheck shell=bash

_aur_packages_complete() {
  local line
  local -a words=("${COMP_WORDS[@]:0:COMP_CWORD+1}")
  COMPREPLY=()
  while IFS= read -r line; do
    case "$line" in
      :files)
        compopt -o filenames
        mapfile -t COMPREPLY < <(compgen -f -- "${words[-1]}")
        return
        ;;
      :dirs)
        compopt -o filenames
        mapfile -t COMPREPLY < <(compgen -d -- "${words[-1]}")
        return
        ;;
      *) COMPREPLY+=("${line%%$'\t'*}") ;;
    esac
  done < <("${words[0]}" __complete "${words[@]:1}" 2>/dev/null)
}

complete -F _aur_packages_complete aur-packages
