# Completion of aur-packages for bash, in ~/.bashrc: source <(aur-packages completion bash)
# bash takes it for ./aur-packages as well, by the name after the last slash.
# shellcheck shell=bash

_aur_packages_complete() {
  local cur=${COMP_WORDS[COMP_CWORD]} prev=${COMP_WORDS[COMP_CWORD - 1]} command='' word i
  local options='' packages=false local_packages=false templates=false
  # The command is the first word after the program's name that isn't an option
  for ((i = 1; i < COMP_CWORD; i++)); do
    word=${COMP_WORDS[i]}
    if [[ "$word" != -* ]]; then
      command=$word
      break
    fi
  done
  if [[ -z "$command" ]]; then
    mapfile -t COMPREPLY < <(compgen -W 'pull push adopt publish updates upgrade check commits build sync setup
      tray commit-msg prepare-commit-msg quoting maintainers list completion help' -- "$cur")
    return
  fi
  # The package to leave out, of the checkout the command works on
  if [[ "$command" == push && "$prev" == --exclude ]]; then
    mapfile -t COMPREPLY < <(compgen -W "$("${COMP_WORDS[0]}" list 2>/dev/null)" -- "$cur")
    return
  fi
  case "$command" in
    pull | adopt | upgrade | quoting) packages=true ;;
    publish)
      if [[ "$prev" == --section ]]; then
        mapfile -t COMPREPLY < <(compgen -W "PowerShell .NET SourceMod Other" -- "$cur")
        return
      fi
      options='--section --adopt' local_packages=true
      ;;
    updates) options='--state --retry' packages=true ;;
    push)
      options='--nocheck --exclude' packages=true
      ;;
    check) options=--manual packages=true ;;
    maintainers) options=--aur packages=true ;;
    commits) options=--update packages=true ;;
    sync) options=--check packages=true ;;
    build)
      case "$prev" in
        --target)
          mapfile -t COMPREPLY < <(compgen -W 'aarch64 aarch64-native' -- "$cur")
          return
          ;;
        --sanitize)
          mapfile -t COMPREPLY < <(compgen -W 'undefined address address,undefined' -- "$cur")
          return
          ;;
        --repo)
          compopt -o filenames
          mapfile -t COMPREPLY < <(compgen -d -- "$cur")
          return
          ;;
      esac
      options='--chroot --local --install --dry-run -n --keep --dotnet-bin --libs-bin --testing --sanitize --target --repo'
      packages=true templates=true
      ;;
    list) options='--templates --local' ;;
    commit-msg | prepare-commit-msg)
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
    tray)
      if ((COMP_CWORD == i + 1)); then
        mapfile -t COMPREPLY < <(compgen -W 'install remove' -- "$cur")
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
  # publish only takes the packages of local/
  if [[ "$local_packages" == true ]]; then
    words+=$("${COMP_WORDS[0]}" list --local 2>/dev/null)$'\n'
  fi
  if [[ "$templates" == true ]]; then
    words+=$("${COMP_WORDS[0]}" list --templates 2>/dev/null)
  fi
  mapfile -t COMPREPLY < <(compgen -W "$words" -- "$cur")
}

complete -F _aur_packages_complete aur-packages
