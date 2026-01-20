# Maintainer: Robin Broda <robin at broda dot me>
# Maintainer: Levente Polyak <anthraxx[at]archlinux[dot]org>

pkgname=ghidra
pkgver=12.0.1
pkgrel=1
_yajsw=13.12
_jsarif=2.1
_protobuf=6.31.0
_psutil=5.9.8
_setuptools=80.9.0
_wheel=0.45.1
_jpype1=1.5.2
_packaging=25.0
pkgdesc='Software reverse engineering framework'
url='https://ghidra-sre.org/'
arch=(x86_64)
license=(
  Apache-2.0
)
depends=(
  'java-environment>=21'
  bash
  python
)
makedepends=(
  'java-environment=21'
  git
  gradle
  grep
  python-build
  python-flit-core
  python-installer
  python-pip
  python-setuptools
  z3
  z3-java
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
  https://files.pythonhosted.org/packages/source/j/jpype1/jpype1-${_jpype1}.tar.gz
  https://files.pythonhosted.org/packages/source/p/packaging/packaging-${_packaging}.tar.gz
)
noextract=(
  AXMLPrinter2.jar
  yajsw-stable-${_yajsw}.zip
  psutil-${_psutil}.tar.gz
)
sha512sums=('1685c68418c0dfa92a64096e16a379d967d9756ed22171eab2b5366b114a56564501808708ba7a65cdd60cec75194eff204b5b9d1bde5965c84edc8135bb4336'
            'b2dfe009e30bb89f84cbc5693c696e523882af1682a14f001570d89d475e72b399ab540a6cb8b027ed1f2358dc47a3bb5c7270237f03bf6f25b761b5dc9b1865'
            'c1168ec913f1fbb0675915d4fd865ec9a8e8573f6c8aedcb6e68166f61f11aeaececc7548d54d78134843c0102c57d6350973f6d3027d0ffdae52a5c57a7f601'
            'ce942efe3e4f45280913122dab121b583ce20d9a86369de8148daf100fa2f4695f59acd79087519c5ce6ac65803ffa068607430760b556abb31e60558c0085e9'
            'ad1b61e7cd9dacbcc5dfa181ed7ed55325eb582e5c104102977e4051c02293c163e16deb6593c8b7cc65ff7b1ee3a636c324c1b05eb6eec9960391b0499a04e0'
            '6ddeed937119a930bb7b9556ff329f054e9429b8457c9a15d99cb105271297117abba587a974d02760bb8b6b244734973a676bdff6b533a53ce587858e48f337'
            '36eb1f219d29c6b9e135936bde2001ad70a971c8069cd0175d3a5325b450e6843a903d3f70043c9f534768ebeab8ab0c544b8f44456555d333f1ed72daa5c18b'
            'df45f00e9eaeae2f27f813f31591590c961da2f6bff15bba6fb2a14d529c221f39b29894b8da408fe49cd4b760840a0e05c4baef377ccfacd9983c0bba83d6d8'
            'b02c294ee2ef7a206fcd80827f790bcad73bf857ab8a473a795752431eacfda85dc53ec5451545b24d9d5c80c71fa10355ba232916c2c1d52534ec54c7d0bb3b'
            '0672602d2e18c3aee71b3e567b0de572bc8613ee3d24a79a655ded23ac08ec4582193225bc0c0ea390ed81cf5efbb46e8afbe0798d14f2235f811f263c25728c')

prepare() {
  cd ghidra-Ghidra_${pkgver}_build

  # Check dependency expectations
  _check_dep "yajsw-stable-${_yajsw}.zip"
  _check_dep "java-sarif-${_jsarif}-modified.jar"
  _check_dep "protobuf-${_protobuf}-"
  _check_dep "psutil-${_psutil}.tar.gz"
  _check_dep "setuptools-${_setuptools}-"
  _check_dep "wheel-${_wheel}-"
  _check_dep "jpype1-${_jpype1}-"
  _check_dep "packaging-${_packaging}-"

  # Copy needed libraries into flat repo folder
  install -Dm 644 \
    ../AXMLPrinter2.jar ../ghidra-data/lib/java-sarif-${_jsarif}-modified.jar \
    -t dependencies/flatRepo
  install -Dm 644 ../psutil-${_psutil}.tar.gz -t dependencies/Debugger-rmi-trace
  install -Dm 644 ../jpype1-${_jpype1}.tar.gz -t dependencies/PyGhidra/

  # Debugger model
  install -Dm 644 ../ghidra-data/Debugger/dbgmodel.tlb -t dependencies/Debugger-agent-dbgeng/

  # YAJSW expects this symlink
  ln -sf ghidra-Ghidra_${pkgver}_build ../ghidra.bin
  install -Dm 644 ../yajsw-stable-${_yajsw}.zip -t dependencies/GhidraServer

  # Add FID datasets
  install -Dm 644 ../ghidra-data/FunctionID/*.fidb -t Ghidra/Features/FunctionID/src/main/fidb

  # Ignore lack of licensing for YAJSW zip, packed FID datasets, and the native binaries
  sed -i '/FileTree tree/a\\t\texclude "yajsw-stable-**.zip"\n\t\texclude "src/main/fidb/**.fidb"\n\t\texclude "os/linux64/**"' gradle/support/ip.gradle

  # z3 dependencies
  install -Dm 644 /usr/lib/libz3* -t dependencies/SymbolicSummaryZ3/os/linux_x86_64
  install -Dm 644 /usr/share/java/com.microsoft.z3.jar -t dependencies/flatRepo
}

_check_dep() {
  local dep=$1
  if ! grep -m1 "${dep}" --quiet gradle/support/fetchDependencies.gradle; then
    error "Dependency expectation failed: ${dep}"
    return 1
  fi
}

build() {
  cd ghidra-Ghidra_${pkgver}_build

  export GRADLE_HOME="$(pwd)/usr/share/java/gradle/"
  export PATH="/usr/lib/jvm/java-21-openjdk/bin:${PATH}"
  export PATH="$(pwd)/usr/share/java/gradle/bin/:${PATH}"

  # Build dependencies
  _build_python_dependency protobuf-${_protobuf} Debugger-rmi-trace
  _build_python_dependency setuptools-${_setuptools} Debugger-rmi-trace PyGhidra
  _build_python_dependency wheel-${_wheel} Debugger-rmi-trace PyGhidra
  _build_python_dependency packaging-${_packaging} PyGhidra
  _build_python_dependency jpype1-${_jpype1} PyGhidra

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
  ln -s /opt/ghidra/support/pyghidraRun "${pkgdir}"/usr/bin/pyghidra
  ln -s /opt/ghidra/support/analyzeHeadless "${pkgdir}"/usr/bin/ghidra-analyzeHeadless
}

# vim: ts=2 sw=2 et:
