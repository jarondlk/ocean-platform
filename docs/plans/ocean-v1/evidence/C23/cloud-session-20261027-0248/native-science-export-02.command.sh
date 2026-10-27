set -euo pipefail
umask 077
cat /sys/fs/cgroup/ocean-c23/cgroup.events
! grep -q '^populated 1$' /sys/fs/cgroup/ocean-c23/cgroup.events
tar --exclude='*/rootfs' -C /var/lib/ocean-c23 -cf /tmp/c23-native-science-20261027-02-evidence.tar \
 operator-acceptance/scientific-import-diagnostic-20261027-03 \
 operator-acceptance/numerics-a-20261027-03 \
 operator-acceptance/numerics-b-20261027-03 \
 operator-acceptance/raster-20261027-03 \
 operator-acceptance/scientific-import-diagnostic-20261027-02 \
 operator-acceptance/numerics-a-20261027-02 \
 operator-acceptance/native-forensic-create-20261027-01 \
 evidence/native-forensic-before-start-01 \
 evidence/network-isolation-20261027-06.json \
 evidence/network-isolation-20261027-07.json \
 evidence/host-positive-controls-20261027-01.json \
 evidence/numerical-comparison-20261027-03.json
chmod 0644 /tmp/c23-native-science-20261027-02-evidence.tar
sha256sum /tmp/c23-native-science-20261027-02-evidence.tar
