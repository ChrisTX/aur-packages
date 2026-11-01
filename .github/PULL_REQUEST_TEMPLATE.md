<!-- A pull request description starts with the sections below, not a title -->
<!-- rumdl-disable-file MD041 -->

## What changes, and why

<!-- The packages and the reason for the change -->

## Checklist

- [ ] One commit per package, with a message like `upgpkg: <pkg> <ver>-<rel>` or `<pkg>: <summary>` (see [CONTRIBUTING.md](https://github.com/ChrisTX/aur-packages/blob/master/CONTRIBUTING.md#commits-and-aurpublish))
- [ ] pkgrel bumped if the built package changes, `.SRCINFO` regenerated
- [ ] `./aur-packages check` passes
- [ ] Built in a clean chroot (`pkgctl build` or `./aur-packages build`), and checked with `namcap`
