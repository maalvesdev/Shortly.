# Container maintenance and security review

[Back to the Shortly README](../README.md)

This page describes container maintenance and preserves the security review performed on **October 27, 2026**. The findings below are a historical snapshot, not a new scan or a guarantee about the images currently available. Advisory data and image contents change over time.

For local setup, environment variables, trusted-proxy configuration, and deployment instructions, see the [development guide](development.md).

## Application image

The [Dockerfile](../Dockerfile) uses Python 3.14 on Debian Trixie. It installs dependencies from [requirements.txt](../requirements.txt), runs `pip check`, and then removes `pip` and its optional bootstrap module, `ensurepip`. These installers contain bundled libraries that Shortly does not need at runtime. The application runs through Gunicorn as a non-root user.

To add a dependency, edit `requirements.txt` and rebuild the image. The optional Python environment on your computer keeps its own pip installation.

Run the following commands from the project root to refresh the base image and dependencies, test the result, restart the local app, and inspect the image:

```powershell
docker compose build --pull --no-cache web
docker compose run --rm web python -m unittest discover -s tests -v
docker compose up --wait
docker scout cves local://shortly-web:latest --locations
```

Docker Scout requires Docker sign-in. Its report can also be viewed through Docker Desktop's image analysis. Inspect package locations to distinguish application dependencies from installer or operating-system components.

## PostgreSQL image updates

The database service uses the official `postgres:18` image in [compose.yaml](../compose.yaml). To check for updates within PostgreSQL 18 and scan the downloaded image:

```powershell
docker compose pull db
docker scout cves local://postgres:18 --locations
```

Pulling an image does not replace the running database container. Before applying an update, save a database backup outside the container and keep the existing named volume. Stay within PostgreSQL 18 for routine updates; a major-version change needs a separate migration procedure.

## Review snapshot: October 27, 2026

The following observations describe the images and package repositories examined on that date. They should be reassessed after image updates, relevant application changes, or before public deployment. Unresolved findings were kept visible in Docker Scout.

### Application image: remaining operating-system findings

- **zlib / CVE-2026-85091:** [Debian's security tracker](https://security-tracker.debian.org/tracker/CVE-2026-85091) marked the installed version vulnerable. The configured stable repositories offered no newer package at the time of review. This finding remained open for rechecking when the base image or stable package was updated. The affected-version range was under discussion; a smaller version number alone did not establish safety.
- **tar / CVE-2025-45582:** [Debian described this issue as disputed](https://security-tracker.debian.org/tracker/CVE-2025-45582). Shortly did not accept or extract archives, so the described archive-extraction scenario was not exposed by the application's features.

### PostgreSQL image: four critical findings

The local `postgres:18` image was already the current official image on October 27, running PostgreSQL 18.6. Its four critical findings pointed to Go 1.24.6 in `/usr/local/bin/gosu`, the helper that switches to the database user during startup.

| Finding | Applicability assessment from the review |
| --- | --- |
| [CVE-2025-68121](https://pkg.go.dev/vuln/GO-2026-4337) | Requires Go TLS session resumption; no TLS calls appeared in the reviewed gosu startup code. |
| [CVE-2026-56857](https://pkg.go.dev/vuln/GO-2026-6604) | Concerns Windows junction handling; the image ran Linux. |
| [CVE-2026-39821](https://pkg.go.dev/vuln/GO-2026-5026) | Concerns HTTP/IDNA hostname conversion; no corresponding calls appeared in the reviewed gosu code. |
| [CVE-2026-78663](https://pkg.go.dev/vuln/GO-2026-6612) | Requires a Go HTTP/2 server; gosu did not run one. |

### PostgreSQL image: high findings and binary analysis

The follow-up scan reported **33 high findings**: 30 in gosu's Go standard library, two in libxml2, and one in zlib.

A binary scan of the actual gosu executable using `govulncheck` v1.9.0 found no affected standard-library symbols for those 30 high and four critical advisories. All 34 CVEs were covered by the checker's advisory data. This supported the source review and [gosu's security policy](https://github.com/tianon/gosu/security).

Binary symbol analysis has limitations and did not establish that the image had no security issues. Docker Scout's alerts remained visible.

### PostgreSQL image: separate user/group parser advisory

The binary check identified one separate medium-severity advisory, [CVE-2026-61801](https://github.com/moby/sys/security/advisories/GHSA-mjcv-p78q-w5fw), in gosu's user/group parser. It required attacker-controlled account files such as `/etc/passwd` or `/etc/group`; Shortly's inputs and volume mounts did not provide that capability.

The dependency was fixed in [gosu 1.20](https://github.com/tianon/gosu/pull/181). The review left this item for rechecking when the official PostgreSQL image adopted that release.

### PostgreSQL image: unresolved Debian findings

Three high-severity Debian findings remained open:

- [libxml2 CVE-2026-74860](https://security-tracker.debian.org/tracker/CVE-2026-74860)
- [libxml2 CVE-2026-86140](https://security-tracker.debian.org/tracker/CVE-2026-86140)
- [zlib CVE-2026-85091](https://security-tracker.debian.org/tracker/CVE-2026-85091)

The configured stable repositories offered no newer versions of those packages at the time of review. Comparing the official `postgres:18-alpine` image did not offer a clear improvement: it retained the same Go findings and had additional findings, so the database image was not changed.

Recheck these observations against fresh image and advisory data when performing future maintenance.
