# Overview

Raman data processing and mineral identification tool, v0.0.1

# Setup

- Open Terminal at folder that contains `gui.py`
- Run command to make virtual environment: `python3.11 -m venv venv`
- Run command to activate virtual environment: `source venv/bin/activate`
- Run command to install necessary packages in virtual environment: `pip install -r requirements.txt`
- Run command to launch the GUI: `python gui.py`

# Usage

- Load a database (top left button; select the `raman_spectra_excellent_and_fair.db` file)
- Load a file for analysis (example file included: `ricolite-a_3a_10s_100p...`
- Enter peak detection parameters (recommended: `width=5`, `rel_height=0.5`, can increase `height` if necessary)
- Click Find Peaks button
- Enter a Tolerance (top right)
- Click Search
- Using the mineral names that appear, enter them into the box in the bottom right and click Search there
- Select a spectrum or spectra and press Plot
- Align X axis if necessary


