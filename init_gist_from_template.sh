#!/usr/bin/env bash

set -e

if [[ -z $1 ]]; then
	echo "Missing Gist URL!" >&2
	exit 1
fi

rm -rf tmp
mkdir tmp
cd tmp
git clone "$1" .
cp ../template/* .
git add -- *.{png,jpg}
git commit -m 'Add images'
git push
