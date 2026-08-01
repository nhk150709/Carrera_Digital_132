# Running as a systemd service

Makes the app start automatically on boot, restart itself if it crashes,
and run in the background permanently -- no manual `cd`/`source
.venv/bin/activate`/`uvicorn` every session.

## Install

Run these on the Pi (assumes the venv is already created per the main
[`README.md`](../README.md)):

```bash
sudo cp deploy/carrera-rms.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable carrera-rms   # start on every boot
sudo systemctl start carrera-rms    # start it right now
```

Check it's actually running:

```bash
sudo systemctl status carrera-rms
```

## Configuring real hardware

Copy the template and edit it (not committed to git):

```bash
cp ~/Carrera_Digital_132/.env.example ~/Carrera_Digital_132/.env
```

`CARRERA_RMS_CU_DEVICE=auto` (scans for a device named `Control_Unit` on
every start) is usually the least fuss -- avoids hardcoding a MAC that
might not even be stable across power cycles. Then:

```bash
sudo systemctl restart carrera-rms
```

Until you set `CARRERA_RMS_CU_DEVICE`, the service runs against the mock
CU -- fine to set up the service now and add real hardware later.

## Logs

The service doesn't print to a visible terminal anymore -- use
journalctl instead:

```bash
journalctl -u carrera-rms -f       # follow live
journalctl -u carrera-rms -n 100   # last 100 lines
```

## After a `git pull`

The service uses the venv's installed packages, so if `requirements.txt`
changed you still need to update them manually, then restart:

```bash
cd ~/Carrera_Digital_132
source .venv/bin/activate
pip install -r requirements.txt
deactivate
sudo systemctl restart carrera-rms
```

## Uninstall

```bash
sudo systemctl disable --now carrera-rms
sudo rm /etc/systemd/system/carrera-rms.service
sudo systemctl daemon-reload
```
