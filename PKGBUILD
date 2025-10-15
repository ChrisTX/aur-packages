# Maintainer: Robin Broda <robin at broda dot me>
# Maintainer: Levente Polyak <anthraxx[at]archlinux[dot]org>

pkgname=ghidra
pkgver=11.3.2
pkgrel=1
_yajsw=13.12
_jsarif=2.1
_protobuf=3.20.3
_psutil=5.9.8
_setuptools=68.0.0
_wheel=0.37.1
pkgdesc='Software reverse engineering framework'
url='https://ghidra-sre.org/'
arch=(x86_64)
license=(
  Apache-2.0
)
depends=(
  'java-environment>=21'
  bash
)
makedepends=(
  'java-environment=21'
  git
  gradle
  python-build
  python-flit-core
  python-installer
  python-pip
  python-setuptools
)
optdepends=(
  'pam: GhidraServer support'
)
options=('!strip')
source=(
  https://github.com/NationalSecurityAgency/ghidra/archive/Ghidra_${pkgver}_build.tar.gz
  "git+https://github.com/NationalSecurityAgency/ghidra-data#tag=Ghidra_${pkgver}"
  https://storage.googleapis.com/google-code-archive-downloads/v2/code.google.com/android4me/AXMLPrinter2.jar
  https://sourceforge.net/projects/yajsw/files/yajsw/yajsw-stable-${_yajsw}/yajsw-stable-${_yajsw}.zip
  https://files.pythonhosted.org/packages/source/p/protobuf/protobuf-${_protobuf}.tar.gz
  https://files.pythonhosted.org/packages/source/p/psutil/psutil-${_psutil}.tar.gz
  https://files.pythonhosted.org/packages/source/s/setuptools/setuptools-${_setuptools}.tar.gz
  https://files.pythonhosted.org/packages/source/w/wheel/wheel-${_wheel}.tar.gz
)
noextract=(
  AXMLPrinter2.jar
  yajsw-stable-${_yajsw}.zip
  psutil-${_psutil}.tar.gz
)
sha512sums=('d86dc44214bb269732c56da8fdf4e13439e1d4927354f8b8b3d3c9bc364ff56e77a53f1355b8a12e93e1916942d6fe43c08a37d371f91533085904506d733a4c'
            'eaf5187894f63016352d4a4bd6276a7df07282b3a64b8ff2d06705148beca09f69d7072c711fe2cebae42f6c53aef0cc0397490ecf3384fa6b8b02b86051c724'
            'c1168ec913f1fbb0675915d4fd865ec9a8e8573f6c8aedcb6e68166f61f11aeaececc7548d54d78134843c0102c57d6350973f6d3027d0ffdae52a5c57a7f601'
            'ce942efe3e4f45280913122dab121b583ce20d9a86369de8148daf100fa2f4695f59acd79087519c5ce6ac65803ffa068607430760b556abb31e60558c0085e9'
            'ae3ca199e7aa0b98634dd89b00fd5e8b04e9b8a840b76406730f14743ef71afdc4e84ade2730dae7958bf82e7b8bb884280394a81c7f9607edb1455df3fee4f6'
            '6ddeed937119a930bb7b9556ff329f054e9429b8457c9a15d99cb105271297117abba587a974d02760bb8b6b244734973a676bdff6b533a53ce587858e48f337'
            'da6d535a0db6eaf477c8c2148efbc2100fd88a14f3adad44d20e22bf52bee3f00fe86547ea650fe653519bd6ff5f9ef033a55bb3a05fed041e88e78cdfb81d7e'
            'c977a740c17abd1fa4b4c2382a33f3ff887baa4231c36990d988cb8531496074e39744786ef6ac0da9c9af4977bce5b2da145377a3ac15eea918f8125bff66ec')

prepare() {
  cd ghidra-Ghidra_${pkgver}_build

  # Copy needed libraries into flat repo folder
  install -Dm 644 \
    ../AXMLPrinter2.jar ../ghidra-data/lib/java-sarif-${_jsarif}-modified.jar \
    -t dependencies/flatRepo
  install -Dm 644 ../psutil-${_psutil}.tar.gz -t dependencies/Debugger-rmi-trace

  # Debugger model
  install -Dm 644 ../ghidra-data/Debugger/dbgmodel.tlb -t dependencies/Debugger-agent-dbgeng/

  # YAJSW expects this symlink
  ln -sf ghidra-Ghidra_${pkgver}_build ../ghidra.bin
  install -Dm 644 ../yajsw-stable-${_yajsw}.zip -t dependencies/GhidraServer

  # Add FID datasets
  install -Dm 644 ../ghidra-data/FunctionID/*.fidb -t Ghidra/Features/FunctionID/src/main/fidb

  # Ignore lack of licensing for YAJSW zip, packed FID datasets, and the native binaries
  sed -i '/FileTree tree/a\\t\texclude "yajsw-stable-**.zip"\n\t\texclude "src/main/fidb/**.fidb"\n\t\texclude "os/linux64/**"' gradle/support/ip.gradle
}

build() {
  cd ghidra-Ghidra_${pkgver}_build

  export GRADLE_HOME="$(pwd)/usr/share/java/gradle/"
  export PATH="/usr/lib/jvm/java-21-openjdk/bin:${PATH}"
  export PATH="$(pwd)/usr/share/java/gradle/bin/:${PATH}"

  # Build dependencies
  _build_python_dependency protobuf-${_protobuf} Debugger-rmi-trace
  _build_python_dependency setuptools-${_setuptools} Debugger-rmi-trace
  _build_python_dependency wheel-${_wheel} Debugger-rmi-trace

  # Ghidra build
  gradle yajswDevUnpack
  gradle buildNatives_linux_x86_64
  gradle sleighCompile
  gradle buildGhidra
}

_build_python_dependency() {
  local folder=$1; shift
  local targets=("$@")
  local target

  msg "Building python dependency ${folder} for ${targets[*]}"
  pushd "../${folder}"
  python -m build --wheel --no-isolation
  for target in "${targets[@]}"; do
    install -Dm 644 dist/*.whl -t "../ghidra-Ghidra_${pkgver}_build/dependencies/${target}"
  done
  popd
}

package() {
  cd ghidra-Ghidra_${pkgver}_build

  # Extract built archive into destination folder
  install -d "${pkgdir}"/{opt,usr/bin}
  _appver=$(grep -oP '(?<=^application.version=).*$' Ghidra/application.properties)
  _relname=$(grep -oP '(?<=^application.release.name=).*$' Ghidra/application.properties)
  bsdtar xf "build/dist/ghidra_${_appver}_${_relname}"_*_linux_x86_64.zip -C "${pkgdir}"/opt

  # Simplify some directory and binary names
  mv "${pkgdir}"/opt/ghidra{_*,}
  ln -s /opt/ghidra/ghidraRun "${pkgdir}"/usr/bin/ghidra
  ln -s /opt/ghidra/support/analyzeHeadless "${pkgdir}"/usr/bin/ghidra-analyzeHeadless
}

# vim: ts=2 sw=2 et:
