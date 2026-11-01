# Completion of aur-packages for fish, which takes it for ./aur-packages as well. Either in
# ~/.config/fish/config.fish: aur-packages completion fish | source
# or saved as ~/.config/fish/completions/aur-packages.fish.

# The packages (or with --templates the build templates) of the checkout the command works on, from
# the command itself
function __aur_packages_list
    set -l program (commandline -opc)[1]
    $program list $argv 2>/dev/null
end

set -l commands pull push updates upgrade check commits build sync setup commit-msg quoting list completion help
set -l none "not __fish_seen_subcommand_from $commands"

complete -c aur-packages -f
complete -c aur-packages -n $none -a pull -d 'Pull the packages from the AUR'
complete -c aur-packages -n $none -a push -d 'Check, then push the packages to the AUR'
complete -c aur-packages -n $none -a updates -d 'Show which packages have a newer upstream version'
complete -c aur-packages -n $none -a upgrade -d 'Upgrade the packages to their latest upstream version'
complete -c aur-packages -n $none -a check -d 'Run the checks of .pre-commit-config.yaml'
complete -c aur-packages -n $none -a commits -d 'Show the upstream commits of the pinned _commit values'
complete -c aur-packages -n $none -a build -d 'Build packages or a template with their dependencies'
complete -c aur-packages -n $none -a sync -d 'Copy templates/package into the packages'
complete -c aur-packages -n $none -a setup -d 'Install the git hooks'
complete -c aur-packages -n $none -a commit-msg -d 'Check a commit message'
complete -c aur-packages -n $none -a quoting -d 'Check the quoting of the metadata arrays'
complete -c aur-packages -n $none -a list -d 'List the packages or the build templates'
complete -c aur-packages -n $none -a completion -d 'Print the completion script of a shell'
complete -c aur-packages -n $none -a help -d 'Show the help'

complete -c aur-packages -n '__fish_seen_subcommand_from pull push updates upgrade check commits build sync quoting' \
    -a '(__aur_packages_list)' -d Package
complete -c aur-packages -n '__fish_seen_subcommand_from push' -l nocheck -d 'Push without running the checks'
complete -c aur-packages -n '__fish_seen_subcommand_from check' -l manual -d 'Also run the checks that only run on request'
complete -c aur-packages -n '__fish_seen_subcommand_from commits' -l update -d 'Rewrite stale _commit values'
complete -c aur-packages -n '__fish_seen_subcommand_from sync' -l check -d 'Only report differences'
complete -c aur-packages -n '__fish_seen_subcommand_from list' -l templates -d 'List the build templates'

set -l build '__fish_seen_subcommand_from build'
complete -c aur-packages -n $build -a '(__aur_packages_list --templates)' -d 'Build template'
complete -c aur-packages -n $build -l chroot -d 'Build in a clean chroot (default)'
complete -c aur-packages -n $build -l local -d 'Build with makepkg -fCd'
complete -c aur-packages -n $build -l install -d 'Install each result of a local build'
complete -c aur-packages -n $build -s n -l dry-run -d 'Print the plan'
complete -c aur-packages -n $build -l keep -d 'Keep the chroot repo'
complete -c aur-packages -n $build -l dotnet-bin -d "Build with Microsoft's .NET"
complete -c aur-packages -n $build -l libs-bin -d 'Build with the libraries from nuget.org'
complete -c aur-packages -n $build -l target -x -a 'aarch64\t"Cross-build for aarch64" aarch64-native\t"Build for aarch64 under QEMU"' \
    -d 'Build for another architecture'
complete -c aur-packages -n $build -l repo -x -a '(__fish_complete_directories)' -d 'Continue in the repo of an earlier --keep'

complete -c aur-packages -n '__fish_seen_subcommand_from commit-msg' -F
complete -c aur-packages -n '__fish_seen_subcommand_from completion' -a 'bash zsh fish pwsh' -d Shell
