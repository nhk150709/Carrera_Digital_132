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

Create `~/Carrera_Digital_132/.env` (not committed to git) with whichever
of these you need:

```
CARRERA_RMS_CU_DEVICE=EF:C4:35:38:1A:0B
CARRERA_RMS_CU_ALLOW_CONTROLLER_WRITES=1
CARRERA_RMS_ARDUINO_PORT=/dev/ttyACM0
```

then `sudo systemctl restart carrera-rms` to pick it up. Until you add
`CARRERA_RMS_CU_DEVICE`, the service runs against the mock CU -- fine to
set up the service now and add real hardware later.

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
