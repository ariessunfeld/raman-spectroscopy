"""Utility functions for raman mineral identification"""

from itertools import combinations

import sqlite3
from tqdm import tqdm
import pandas as pd

import numpy as np
from scipy.sparse import csc_matrix, eye, diags
from scipy.sparse.linalg import spsolve
from scipy.signal import find_peaks

def fetch_filename_and_peaks_filtered(database_path, peaks_set, tol):
    """Like filter_spectra_byinclusion but returns peaks as well"""
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()
    
    # Create the inclusion criteria for each peak in the set
    inclusion_conditions = []
    for peak in peaks_set:
        condition = "(strongest_peak >= ? AND strongest_peak <= ?)"
        inclusion_conditions.append((condition, peak - tol, peak + tol))
    
    # Build the SQL query
    query_conditions = " OR ".join([cond[0] for cond in inclusion_conditions])
    query_values = [val for cond in inclusion_conditions for val in cond[1:]]
    query = f"""
    SELECT filename, peaks
    FROM Spectra
    WHERE {query_conditions};
    """
    
    # Execute the SQL query
    cursor.execute(query, query_values)
    matching_rows = cursor.fetchall()
    
    conn.close()
    
    return matching_rows

def peaks_within_tolerance(known_peaks, unknown_peak, tol):
    """Check if the unknown peak is within tolerance of any of the known peaks."""
    for peak in known_peaks:
        if abs(peak - unknown_peak) <= tol:
            return True
    return False

def check_peak_superset(db_peaks, unknown_peaks, tol):
    """Check if db_peaks is a superset of unknown_peaks (within the given tolerance)."""
    for peak in unknown_peaks:
        if not peaks_within_tolerance(db_peaks, peak, tol):
            return False
    return True

def find_spectrum_matches(database_path, unknown_peaks, tol):
    """
    Find potential mineral combinations in the database that match the unknown spectrum.
    
    Parameters:
    - database_path: path to the SQLite database
    - unknown_peaks: list of peaks from the unknown spectrum
    - tol: the tolerance
    
    Returns:
    - List of combinations (filename sets) that match the unknown spectrum
    """
    
    rows = fetch_filename_and_peaks_filtered(database_path, unknown_peaks, tol)
    filenames = [row[0] for row in rows]
    db_peak_sets = [set(eval(row[1])) for row in rows]
    
    potential_matches = {1: [], 2: [], 3: []}
    
    # Check singles, pairs, and triples
    for r in range(1, 4):
        for combo_indices in tqdm(combinations(range(len(filenames)), r)):
            combined_peaks = set().union(*[db_peak_sets[i] for i in combo_indices])
            if check_peak_superset(combined_peaks, unknown_peaks, tol):
                potential_matches[r].append([filenames[i] for i in combo_indices])
    
    return potential_matches

def get_unique_mineral_combinations_optimized(database_path, combos):
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()
    
    # Fetch all filenames and their corresponding names from the Spectra table
    cursor.execute("SELECT filename, names FROM Spectra")
    filename_to_name = dict(cursor.fetchall())
    
    unique_combos = set()
    
    for combo in combos:
        # Lookup mineral names for the filenames in the combo using the in-memory dictionary
        names = [filename_to_name[filename] for filename in combo]
        names = tuple(sorted(names))
        unique_combos.add(names)
    
    conn.close()
    return unique_combos

def get_lines(file):
    with open(file, 'r') as f:
        lines = f.readlines()
    return lines

def axis_to_number(axis):
    if axis == 'x':
        return 0
    elif axis == 'y':
        return 1
    else:
        raise ValueError('Please enter x or y for `axis` parameter')

def get_data(file, axis='x'):
    # Extract data (x or y) from a .txt spectrum file

    n = axis_to_number(axis)
    
    data = []
    lines = get_lines(file)
    first_line = lines[0]
    if first_line.startswith('#'):
        for line in lines:
            if not line.startswith('##') and line.strip() and not line.startswith('800, -'):
                data += [float(line.split(', ')[n])]
        return data
    else: # Assume whitespace-separated
        for line in lines:
            line = line.strip()
            if line:
                data += [float(line.split()[n])]
        return data[::-1]


def get_xy_from_file(file):
    if file.name.endswith('.txt'):
        try:
            x = get_data(file, axis='x')
            y = get_data(file, axis='y')
        except:
            raise ValueError(f'Could not extract x and y from {file}. Ensure format matches RRUFF .txt file format.')
        return np.array(x), np.array(y)
    elif file.name.endswith('.csv'):
        # TODO add error handling
        df = pd.read_csv(file)
        if 'x' in df.columns and 'y' in df.columns: # TODO Make this more flexible
            return np.array(df['x']), np.array(df['y'])
        
def deserialize(vec):
    return np.array(eval(vec))

def baseline_als(y, lam=1e5, p=0.05, niter=1000):
    L = len(y)
    valid_indices = ~np.isnan(y)
    y_valid = y[valid_indices]
    
    L_valid = len(y_valid)  # Length of valid y values
    D = diags([1, -2, 1], [0, -1, -2], shape=(L_valid, L_valid-2))
    D = lam * D.dot(D.transpose())
    w = np.ones(L_valid)
    W = diags([w], [0], shape=(L_valid, L_valid))
    
    for i in range(niter):
        W.setdiag(w)
        Z = W + D
        z_valid = spsolve(csc_matrix(Z), w*y_valid)
        w = p * (y_valid > z_valid) + (1-p) * (y_valid < z_valid)
    
    z = np.empty_like(y)
    z[:] = np.nan
    z[valid_indices] = z_valid
    return z

def get_peaks(x, y, width, rel_height, height, prominence):
    peaks, _ = find_peaks(y, width=width, rel_height=rel_height, height=height, prominence=prominence)
    return x[peaks], y[peaks]