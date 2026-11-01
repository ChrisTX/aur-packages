# Completion of aur-packages and ./aur for bash, in ~/.bashrc: source <(aur-packages completion bash)
# Not for aur, which is aurutils'.
# shellcheck shell=bash

_aur_packages_complete() {
  local cur=${COMP_WORDS[COMP_CWORD]} prev=${COMP_WORDS[COMP_CWORD - 1]} command='' word i
  local options='' packages=false templates=false
  # The command is the first word after the program's name that isn't an option
  for ((i = 1; i < COMP_CWORD; i++)); do
    word=${COMP_WORDS[i]}
    if [[ "$word" != -* ]]; then
      command=$word
      break
    fi
  done
  if [[ -z "$command" ]]; then
    mapfile -t COMPREPLY < <(compgen -W 'pull push updates upgrade check commits build sync setup
      commit-msg list completion help' -- "$cur")
    return
  fi
  case "$command" in
    pull | updates | upgrade) packages=true ;;
    push) options=--nocheck packages=true ;;
    check) options=--manual packages=true ;;
    commits) options=--update packages=true ;;
    sync) options=--check packages=true ;;
    build)
      case "$prev" in
        --target)
          mapfile -t COMPREPLY < <(compgen -W 'aarch64 aarch64-native' -- "$cur")
          return
          ;;
        --repo)
          compopt -o filenames
          mapfile -t COMPREPLY < <(compgen -d -- "$cur")
          return
          ;;
      esac
      options='--chroot --local --install --dry-run -n --keep --dotnet-bin --libs-bin --target --repo'
      packages=true templates=true
      ;;
    list) options=--templates ;;
    commit-msg)
      if ((COMP_CWORD == i + 1)); then
        compopt -o filenames
        mapfile -t COMPREPLY < <(compgen -f -- "$cur")
      fi
      return
      ;;
    completion)
      if ((COMP_CWORD == i + 1)); then
        mapfile -t COMPREPLY < <(compgen -W 'bash zsh fish pwsh' -- "$cur")
      fi
      return
      ;;
    *) return ;;
  esac
  if [[ "$cur" == -* ]]; then
    mapfile -t COMPREPLY < <(compgen -W "$options" -- "$cur")
    return
  fi
  local words=''
  # The packages of the checkout the command works on, from the command itself
  if [[ "$packages" == true ]]; then
    words+=$("${COMP_WORDS[0]}" list 2>/dev/null)$'\n'
  fi
  if [[ "$templates" == true ]]; then
    words+=$("${COMP_WORDS[0]}" list --templates 2>/dev/null)
  fi
  mapfile -t COMPREPLY < <(compgen -W "$words" -- "$cur")
}

complete -F _aur_packages_complete aur-packages ./aur
