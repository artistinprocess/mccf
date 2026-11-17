# Installing MCCF V5

1. Unzip this release over your `mccf_full` folder (keep folder names). It adds and replaces files; it does not delete yours. Your own scenes, avatars and audio are not touched.
2. `pip install flask flask-cors`
3. `python mccf_api.py` and open http://localhost:5000/static/mccf_launcher.html
4. To check the copy: `bash verify_install.sh` (OK means the file matches this release).

Not in the zip, bring your own: your audio under X3DAssets/media, and the Cindy avatar (see NOTICE). See README.md and docs/guide/.
