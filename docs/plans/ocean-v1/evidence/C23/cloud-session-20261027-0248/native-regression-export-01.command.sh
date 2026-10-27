set -euo pipefail
umask 077
cat /sys/fs/cgroup/ocean-c23/cgroup.events
! grep -q '^populated 1$' /sys/fs/cgroup/ocean-c23/cgroup.events
tar --exclude='*/rootfs' -C /var/lib/ocean-c23 -cf /tmp/c23-native-regression-20261027-01-evidence.tar \
 operator-acceptance/namespaces-native-20261027-01 \
 operator-acceptance/containment-native-20261027-01 \
 operator-acceptance/cancel-native-20261027-01
chmod 0644 /tmp/c23-native-regression-20261027-01-evidence.tar
sha256sum /tmp/c23-native-regression-20261027-01-evidence.tar
