#!/bin/bash
cd /loc_pool/data/photo
for f in *.HEIC; do
	echo "$f"
	heif-convert -q 100 -o "${f%.HEIC}.jpg" "$f" 
done

#sudo apt install libheif-examples
