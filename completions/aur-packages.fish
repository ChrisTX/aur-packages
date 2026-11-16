# Completion of aur-packages for fish, which takes it for ./aur-packages as well. Either in
# ~/.config/fish/config.fish: aur-packages completion fish | source
# or saved as ~/.config/fish/completions/aur-packages.fish. The candidates come from the program
# itself (aur-packages __complete), so they always match the checkout's commands.

function __aur_packages_complete
    set -l words (commandline -opc)
    set -l current (commandline -ct)
    set -l lines ($words[1] __complete $words[2..-1] "$current" 2>/dev/null)
    switch "$lines[1]"
        case :files
            __fish_complete_path "$current"
        case :dirs
            __fish_complete_directories "$current"
        case '*'
            printf '%s\n' $lines
    end
end

complete -c aur-packages -f -a '(__aur_packages_complete)'
