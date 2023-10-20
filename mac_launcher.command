#!/bin/bash

# Get the directory where the script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change directory to the script location
cd $DIR

# Check if virtual environment exists
if [ ! -d "venv" ]; then
  python3.11 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
else
  source venv/bin/activate
fi

# Start the updater
python updater.py

# After updates, run the main program from the latest version
VERSION_FOLDER=$(ls | grep "v[0-9]\+\.[0-9]\+\.[0-9]\+$" | sort -V | tail -n 1)
cd $VERSION_FOLDER
python gui.py

