#!/bin/sh
# Fetch the joined table of Gard, Hasterok & Halpin (2019), v1.1.0,
# doi:10.5281/zenodo.3359791, CC-BY-4.0, into sources/gard2019/.
# Resumable: Zenodo closed two transfers abruptly on 10 Nov (curl error 56),
# so every attempt continues from the bytes already on disk, and the file is
# accepted only when its MD5 equals the one in the Zenodo record.
cd "/d/NASA hacathon/sources/gard2019" || exit 1
WANT=9b97b54887ee7184c6650c845b4e92d4
URL="https://zenodo.org/records/3359791/files/complete.zip?download=1"
n=0
while [ $n -lt 60 ]; do
  n=$((n+1))
  curl -L --fail -sS -C - --retry 3 --retry-delay 5 -o complete.zip "$URL"
  rc=$?
  size=$(stat -c %s complete.zip 2>/dev/null || echo 0)
  echo "attempt $n rc=$rc size=$size"
  if [ "$size" -ge 192615473 ]; then break; fi
  sleep 5
done
GOT=$(md5sum complete.zip | cut -d' ' -f1)
echo "md5 $GOT want $WANT"
[ "$GOT" = "$WANT" ] && echo "COMPLETE-OK" || echo "COMPLETE-BAD"
