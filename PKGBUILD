# Maintainer: Bruno Pagani <archange@archlinux.org>
# Maintainer: Filipe Laíns (FFY00) <lains@archlinux.org>
# Maintainer: Frederik Schwan <freswa at archlinux dot org>
# Contributor: Mirco Tischler <mt-ml at gmx dot de>

pkgbase=fwupd
pkgname=(
  fwupd
  fwupd-docs
)
pkgver=2.0.8
pkgrel=1
pkgdesc="Simple daemon to allow session software to update firmware"
arch=(x86_64)
url='https://github.com/fwupd/fwupd'
license=(LGPL-2.1-or-later)
depends=(
  bash
  bluez
  curl
  flashrom
  fwupd-efi
  gcc-libs
  glib2
  glibc
  gnutls
  hicolor-icon-theme
  json-glib
  libarchive
  libcbor
  libdrm
  libjcat
  libmbim
  libmm-glib
  libqmi
  libusb
  libxmlb
  passim
  polkit
  protobuf-c
  python
  shared-mime-info
  sqlite
  systemd-libs
  tpm2-tss
  xz
  zlib
)
makedepends=(
  bash-completion
  gi-docgen
  git
  gnu-efi-libs
  gobject-introspection
  meson
  noto-fonts
  noto-fonts-cjk
  pandoc
  python-cairo
  python-dbus
  python-dbusmock
  python-gobject
  python-pillow
  umockdev
  vala
  valgrind
)
source=(
  "git+https://github.com/fwupd/fwupd.git#tag=${pkgver}?signed"
  fwupd.sysusers
)
sha512sums=('034422b26da89953430fca20c730cb5be1304dca9bce45aa6180f8ddb1c6d02ba03d9a7c16c01c0893f3043770cfa750adf485699eba21e6652302433925dbf1'
            'f9a99c60786a2b98e0de439a9288af61b2c0716f8339a4c93e2df7108d2a7f9ef8128967dcaa1e12022ffa647945bf5eb3749e38cac83e00a28cbc5b015fbee9')
b2sums=('7e383963d9635f2335b97f00733e6234db6ba003cd1f93b20cb5c7d815e90a049e1c5d121ac8a312494fea4af39d70f4f188fe312abc97d2b389d318f32c5c7e'
        'c294c6dd324c0ad0d752affdc459d427d34f4bf865def099ac0e25db6b5dfbfcf645ca325e4e7732d1256e75c624ff27094d5c814726909c7e348128a9dd93f9')
validpgpkeys=(163EB50119225DB3DF8F49EA17ACBA8DFA970E17) # Richard Hughes <richard@hughsie.com>

build() {
  local meson_options=(
    -D docs=enabled
    -D efi_binary=false
    -D supported_build=enabled
    -D systemd_unit_user=fwupd
  )

  arch-meson ${pkgname} build "${meson_options[@]}"
  meson compile -C build
}

check() {
  meson test -C build --print-errorlogs
}

_pick() {
  local p="$1" f d; shift
  for f; do
    d="$srcdir/$p/${f#$pkgdir/}"
    mkdir -p "$(dirname "$d")"
    mv "$f" "$d"
    rmdir -p --ignore-fail-on-non-empty "$(dirname "$f")"
  done
}

package_fwupd() {
  depends+=(
    libarchive.so
    libblkid.so
    libcbor.so
    libcurl.so
    libjson-glib-1.0.so
    libmm-glib.so
    libpassim.so
    libprotobuf-c.so
    libqmi-glib.so
  )
  optdepends=(
    'python-dbus: Firmware packaging tools'
    'python-gobject: Firmware packaging tools'
    'udisks2: UEFI firmware upgrade support'
  )
  provides=(libfwupd.so)
  backup=(
    'etc/fwupd/fwupd.conf'
    'etc/fwupd/remotes.d/lvfs-testing.conf'
    'etc/fwupd/remotes.d/lvfs.conf'
    'etc/fwupd/remotes.d/vendor-directory.conf'
  )

  meson install -C build --destdir "${pkgdir}"
  # Add fwupd user https://bugs.archlinux.org/task/79653
  install -D -m644 fwupd.sysusers "${pkgdir}"/usr/lib/sysusers.d/fwupd.conf
  # Remove the tests
  rm -r "${pkgdir}"/usr/{lib,share}/installed-tests/
  # Conflicts with the dbxtool package
  mv "${pkgdir}"/usr/bin/{,fwupd-}dbxtool
  mv "${pkgdir}"/usr/share/man/man1/{,fwupd-}dbxtool.1
  # Remove msr module-load config as it is built-in
  rm "${pkgdir}"/usr/lib/modules-load.d/fwupd-msr.conf
  rmdir "${pkgdir}"/usr/lib/modules-load.d

  _pick docs "${pkgdir}"/usr/share/doc/{,fwupd/}{libfwupdplugin,libfwupd}
}

package_fwupd-docs() {
  pkgdesc="Simple daemon to allow session software to update firmware - documentation"
  depends=()
  mv docs/* "${pkgdir}"
}
