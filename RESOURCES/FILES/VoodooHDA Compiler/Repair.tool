#!/bin/sh

sudo chown -R root:wheel /Library/Extensions/VoodooHDA.kext
sudo kextutil -v /Library/Extensions/VoodooHDA.kext