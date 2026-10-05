#!/bin/bash -e
# files/repo is copied in by pi-gen/build.sh: install.sh, src, systemd, config.
install -d "${ROOTFS_DIR}/tmp/openprusacamera"
cp -a files/repo/. "${ROOTFS_DIR}/tmp/openprusacamera/"

on_chroot << EOF
/tmp/openprusacamera/install.sh --camera csi --user "${FIRST_USER_NAME}"
rm -rf /tmp/openprusacamera
EOF
