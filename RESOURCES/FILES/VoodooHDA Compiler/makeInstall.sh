#!/bin/sh

#  makeInstall.sh
#  
#
#  Created by Rodion Shingarev on 27.03.21.
#
cd "$(dirname "$0")"
find . -name '.*' -type f -delete
pkgbuild --component *.kext --install-location  /L*/E* Kext.pkg
pkgbuild --component *.prefPane --install-location  ~/Library/PreferencePanes prefpane.pkg
pkgbuild --root getdump --identifier GetDump --install-location  /opt/local/bin getdump.pkg
productbuild --synthesize --package Kext.pkg --package prefpane.pkg --package getdump.pkg dist.xml
productbuild  --distribution dist.xml VoodooHDA.pkg

