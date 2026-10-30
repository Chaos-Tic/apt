# Chaos-Tic apt repository

An apt repository for Debian 12+ and Ubuntu 24.04+ with the packages of
Chaos-Tic's projects, served by GitHub Pages at
<https://chaos-tic.github.io/apt>. `apt upgrade` installs new releases.

## Install

```sh
sudo curl -fsSLo /usr/share/keyrings/chaos-tic.gpg https://chaos-tic.github.io/apt/chaos-tic-apt.gpg
echo "deb [signed-by=/usr/share/keyrings/chaos-tic.gpg] https://chaos-tic.github.io/apt stable main" |
  sudo tee /etc/apt/sources.list.d/chaos-tic.list
sudo apt update
sudo apt install lorenz lyapunov
```

The key is limited to this repository by `signed-by`. Its fingerprint is
`B968 F27E 534B 7AD3 2C2A 026A C874 EC5C A8A6 42AE`.

## Packages

| Package | Project |
| --- | --- |
| `lorenz` | [Lorenz](https://github.com/Chaos-Tic/Lorenz): local file conversion with radial wheels |
| `chaostictool` | [ChaosticTool](https://github.com/Chaos-Tic/Chaostic-Tool): terminal and desktop interfaces for authorized security testing; Debian 13+ / Ubuntu 24.04+ (replaces the former `chaostictool-desktop`) |
| `lyapunov` | [Lyapunov](https://github.com/Chaos-Tic/Lyapunov): save an activity as a card and resume it later |

## How it works

`projects.txt` lists the projects. The *Publish* workflow downloads the `.deb`
files of each project's latest release (built and tested by that project's
CI), indexes them with `apt-ftparchive`, signs the index and deploys it to
GitHub Pages. It runs every hour, on each push, by hand, and when a
project sends a `repository_dispatch` event. Adding a project is one line in
`projects.txt`. An optional second column selects a tag prefix, e.g. `v` or
`desktop-v`, for projects that publish multiple editions in one repository.

## Channel audit

The *Channels* workflow (`channels.yml`, `channels.py`, `channels.json`)
compares each project's latest release with the versions served by this
repository, the Launchpad PPAs, Fedora COPR, the AUR and winget, twice a week
and on demand. When a channel lags or its last build failed, the run fails
and the issue *Distribution channels lag behind* is opened or refreshed with
the table; it is closed once every channel is aligned. A channel that stays
behind on purpose is listed under `frozen` in `channels.json` with the reason.
