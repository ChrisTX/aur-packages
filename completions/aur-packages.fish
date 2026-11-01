# Completion of aur-packages and ./aur for fish, not for aur, which is aurutils'. Either in
# ~/.config/fish/config.fish: aur-packages completion fish | source
# or saved as ~/.config/fish/completions/aur-packages.fish.

# Whether the command line is one of this completion's: aur-packages, or the script of a checkout of
# the AUR packages (./aur). fish looks up ./aur as aur, which is aurutils', so the completions for aur
# all have this condition.
function __aur_packages_ours
    set -l program (commandline -opc)[1]
    test "$program" = aur-packages; and return
    string match -q -- '*/aur' $program; and test -d (path dirname -- $program)/templates/package
end

# The packages (or with --templates the build templates) of the checkout the command works on, from
# the command itself
function __aur_packages_list
    set -l program (commandline -opc)[1]
    $program list $argv 2>/dev/null
end

# Adds a completion for aur-packages and ./aur, with the condition $argv[1]
function __aur_packages_complete
    set -l condition "__aur_packages_ours; and $argv[1]"
    complete -c aur-packages -n $condition $argv[2..]
    complete -c aur -n $condition $argv[2..]
end

set -l commands pull push updates upgrade check commits build sync setup commit-msg list completion help
set -l none "not __fish_seen_subcommand_from $commands"

__aur_packages_complete true -f
__aur_packages_complete $none -a pull -d 'Pull the packages from the AUR'
__aur_packages_complete $none -a push -d 'Check, then push the packages to the AUR'
__aur_packages_complete $none -a updates -d 'Show which packages have a newer upstream version'
__aur_packages_complete $none -a upgrade -d 'Upgrade the packages to their latest upstream version'
__aur_packages_complete $none -a check -d 'Run the checks of .pre-commit-config.yaml'
__aur_packages_complete $none -a commits -d 'Show the upstream commits of the pinned _commit values'
__aur_packages_complete $none -a build -d 'Build packages or a template with their dependencies'
__aur_packages_complete $none -a sync -d 'Copy templates/package into the packages'
__aur_packages_complete $none -a setup -d 'Install the git hooks'
__aur_packages_complete $none -a commit-msg -d 'Check a commit message'
__aur_packages_complete $none -a list -d 'List the packages or the build templates'
__aur_packages_complete $none -a completion -d 'Print the completion script of a shell'
__aur_packages_complete $none -a help -d 'Show the help'

__aur_packages_complete '__fish_seen_subcommand_from pull push updates upgrade check commits build sync' \
    -a '(__aur_packages_list)' -d Package
__aur_packages_complete '__fish_seen_subcommand_from push' -l nocheck -d 'Push without running the checks'
__aur_packages_complete '__fish_seen_subcommand_from check' -l manual -d 'Also run the checks that only run on request'
__aur_packages_complete '__fish_seen_subcommand_from commits' -l update -d 'Rewrite stale _commit values'
__aur_packages_complete '__fish_seen_subcommand_from sync' -l check -d 'Only report differences'
__aur_packages_complete '__fish_seen_subcommand_from list' -l templates -d 'List the build templates'

set -l build '__fish_seen_subcommand_from build'
__aur_packages_complete $build -a '(__aur_packages_list --templates)' -d 'Build template'
__aur_packages_complete $build -l chroot -d 'Build in a clean chroot (default)'
__aur_packages_complete $build -l local -d 'Build with makepkg -fCd'
__aur_packages_complete $build -l install -d 'Install each result of a local build'
__aur_packages_complete $build -s n -l dry-run -d 'Print the plan'
__aur_packages_complete $build -l keep -d 'Keep the chroot repo'
__aur_packages_complete $build -l dotnet-bin -d "Build with Microsoft's .NET"
__aur_packages_complete $build -l libs-bin -d 'Build with the libraries from nuget.org'
__aur_packages_complete $build -l target -x -a 'aarch64\t"Cross-build for aarch64" aarch64-native\t"Build for aarch64 under QEMU"' \
    -d 'Build for another architecture'
__aur_packages_complete $build -l repo -x -a '(__fish_complete_directories)' -d 'Continue in the repo of an earlier --keep'

__aur_packages_complete '__fish_seen_subcommand_from commit-msg' -F
__aur_packages_complete '__fish_seen_subcommand_from completion' -a 'bash zsh fish pwsh' -d Shell
