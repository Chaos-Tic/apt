#!/usr/bin/env python3
"""Compares each project's latest GitHub release with what the distribution
channels serve (apt repository, Launchpad PPA, Fedora COPR, AUR, winget) and
prints a Markdown report. Exit status 1 when a channel lags or is broken.

    channels.py [channels.json] [--summary FILE]

Only public APIs are used; GITHUB_TOKEN, when set, raises the GitHub rate limit.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

GITHUB_API = "https://api.github.com"
WINGET_REPO = "microsoft/winget-pkgs"
APT_INDEX = "https://chaos-tic.github.io/apt/dists/stable/main/binary-amd64/Packages"
TIMEOUT = 30


def fetch(url, accept="application/json"):
    headers = {"Accept": accept, "User-Agent": "chaos-tic-channels"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith(GITHUB_API):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read().decode()


def fetch_json(url):
    return json.loads(fetch(url))


def version_key(version):
    """Orders dotted versions numerically; non-numeric parts sort first."""
    return tuple(int(part) if part.isdigit() else -1 for part in re.split(r"[.\-~+]", version))


def upstream(project):
    """The version of the latest published release whose tag has the prefix."""
    prefix = project.get("tag_prefix", "")
    for release in fetch_json(f"{GITHUB_API}/repos/{project['github']}/releases?per_page=30"):
        tag = release["tag_name"]
        if release["draft"] or release["prerelease"] or not tag.startswith(prefix):
            continue
        return tag[len(prefix):]
    raise LookupError("no release")


def apt_version(package, index):
    versions = []
    for stanza in index.split("\n\n"):
        if re.search(rf"^Package: {re.escape(package)}$", stanza, re.M):
            match = re.search(r"^Version: (\S+)", stanza, re.M)
            if match:
                versions.append(match.group(1))
    return max(versions, key=version_key) if versions else None


def ppa_versions(project):
    """{series: version} of the sources currently published in the PPA."""
    owner, name = project["ppa"].split("/")
    url = (f"https://api.launchpad.net/devel/~{owner}/+archive/ubuntu/{name}"
           f"?ws.op=getPublishedSources&status=Published"
           f"&source_name={project['ppa_source']}&exact_match=true")
    out = {}
    for entry in fetch_json(url).get("entries", []):
        series = entry["distro_series_link"].rsplit("/", 1)[-1]
        version = entry["source_package_version"].split("-")[0]
        if series not in out or version_key(version) > version_key(out[series]):
            out[series] = version
    return out


def copr_status(project):
    """(version, build state) of the latest COPR build of the package."""
    owner, name = project["copr"].split("/")
    data = fetch_json("https://copr.fedorainfracloud.org/api_3/package"
                      f"?ownername={owner}&projectname={name}&packagename={name}"
                      "&with_latest_build=true")
    build = (data.get("builds") or {}).get("latest") or {}
    version = (build.get("source_package") or {}).get("version")
    return (version.split("-")[0] if version else None), build.get("state")


def aur_version(name):
    data = fetch_json(f"https://aur.archlinux.org/rpc/v5/info?arg[]={name}")
    results = data.get("results") or []
    return results[0]["Version"].split("-")[0] if results else None


def winget_version(identifier):
    """The highest version published in winget-pkgs, or None when absent."""
    publisher, name = identifier.split(".", 1)
    path = f"manifests/{publisher[0].lower()}/{publisher}/{name.replace('.', '/')}"
    try:
        entries = fetch_json(f"{GITHUB_API}/repos/{WINGET_REPO}/contents/{path}")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    versions = [e["name"] for e in entries if e["type"] == "dir" and e["name"][:1].isdigit()]
    return max(versions, key=version_key) if versions else None


def check(project, apt_index):
    """(latest release, rows of (channel, served version, status, note))."""
    want = upstream(project)
    frozen = project.get("frozen", {})
    rows = []

    def row(channel, got, ok=None, note=""):
        if channel in frozen:
            rows.append((channel, got or "-", "frozen", frozen[channel]))
            return
        if ok is None:
            ok = got is not None and version_key(got) >= version_key(want)
        rows.append((channel, got or "-", "ok" if ok else "LAG", note))

    def guarded(channel, call):
        try:
            call()
        except Exception as error:  # a channel API that fails is a finding, not a crash
            rows.append((channel, "?", "ERROR", f"{type(error).__name__}: {error}"))

    def ppa():
        served = ppa_versions(project)
        if not served:
            row("ppa", None, False, "nothing published")
        for series, version in sorted(served.items()):
            row(f"ppa:{series}", version)

    def copr():
        version, state = copr_status(project)
        if state not in (None, "succeeded"):
            row("copr", version, False, f"latest build {state}")
        else:
            row("copr", version)

    def winget():
        version = winget_version(project["winget"])
        note = "" if version else "not in winget-pkgs yet (the first submission is manual)"
        row("winget", version, note=note)

    if "apt" in project:
        guarded("apt", lambda: row("apt", apt_version(project["apt"], apt_index)))
    if "ppa" in project:
        guarded("ppa", ppa)
    if "copr" in project:
        guarded("copr", copr)
    if "aur" in project:
        guarded("aur", lambda: row("aur", aur_version(project["aur"])))
    if "winget" in project:
        guarded("winget", winget)
    return want, rows


def main(argv):
    config_path = "channels.json"
    summary_path = None
    args = iter(argv[1:])
    for arg in args:
        if arg == "--summary":
            summary_path = next(args)
        else:
            config_path = arg
    with open(config_path, encoding="utf-8") as handle:
        projects = json.load(handle)["projects"]
    apt_index = fetch(APT_INDEX, accept="text/plain")

    lines = ["# Distribution channels", ""]
    problems = 0
    for project in projects:
        try:
            want, rows = check(project, apt_index)
        except Exception as error:
            lines += [f"## {project['name']}: ERROR {type(error).__name__}: {error}", ""]
            problems += 1
            continue
        lines += [f"## {project['name']} (latest release {want})", "",
                  "| Channel | Serves | Status | Note |", "| --- | --- | --- | --- |"]
        for channel, got, status, note in rows:
            lines.append(f"| {channel} | {got} | {status} | {note} |")
            if status in ("LAG", "ERROR"):
                problems += 1
        lines.append("")
    report = "\n".join(lines)
    print(report)
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(report + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
