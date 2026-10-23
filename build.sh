#!/usr/bin/env bash
# Builds the apt repository in public/ from the .deb files of the latest
# release of each project in projects.txt, signed with the key in
# $APT_SIGNING_KEY (ASCII-armored secret key). Needs gh, apt-utils, gpg.
set -euo pipefail
rm -rf public pool-download
mkdir -p public/pool/main pool-download
while read -r repo tag_prefix; do
    case $repo in ''|'#'*) continue ;; esac
    name=$(basename "$repo" | tr '[:upper:]' '[:lower:]')
    mkdir -p "public/pool/main/$name"
    release_args=()
    if [ -n "${tag_prefix:-}" ]; then
        # One repository can publish separate CLI and desktop release streams.
        tag=$(gh release list --repo "$repo" --exclude-drafts --exclude-pre-releases --limit 100 \
            --json tagName --jq "map(.tagName) | map(select(startswith(\"$tag_prefix\"))) | first // empty")
        [ -n "$tag" ] || { echo "No published release for $repo ($tag_prefix)" >&2; exit 1; }
        release_args+=("$tag")
    fi
    gh release download "${release_args[@]}" --repo "$repo" --pattern '*.deb' --dir "public/pool/main/$name" --clobber
done <projects.txt

cd public
for arch in amd64 arm64; do
    mkdir -p "dists/stable/main/binary-$arch"
    apt-ftparchive --arch "$arch" packages pool >"dists/stable/main/binary-$arch/Packages"
    gzip -9kf "dists/stable/main/binary-$arch/Packages"
done
apt-ftparchive \
    -o APT::FTPArchive::Release::Origin=Chaos-Tic \
    -o APT::FTPArchive::Release::Label=Chaos-Tic \
    -o APT::FTPArchive::Release::Suite=stable \
    -o APT::FTPArchive::Release::Codename=stable \
    -o APT::FTPArchive::Release::Architectures='amd64 arm64' \
    -o APT::FTPArchive::Release::Components=main \
    -o APT::FTPArchive::Release::Description='Chaos-Tic projects for Debian and Ubuntu' \
    release dists/stable >dists/stable/Release

export GNUPGHOME=$(mktemp -d)
trap 'rm -rf "$GNUPGHOME"' EXIT
gpg --batch --quiet --import <<<"$APT_SIGNING_KEY"
gpg --batch --yes --armor --detach-sign -o dists/stable/Release.gpg dists/stable/Release
gpg --batch --yes --clearsign -o dists/stable/InRelease dists/stable/Release
cp ../chaos-tic-apt.gpg .
cp ../index.html .
