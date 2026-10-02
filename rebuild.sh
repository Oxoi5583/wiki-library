python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
git fetch --all && git reset --hard origin/$(git branch --show-current)
python build.py --output "/var/wiki/html/library"
