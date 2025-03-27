"""This module contains the code for the GUI"""

import os
import sys
from pathlib import Path
import json
import threading
from enum import Enum

from PyQt6.QtWidgets import (
    QApplication, 
    QMainWindow, 
    QWidget, 
    QVBoxLayout, 
    QHBoxLayout, 
    QSizePolicy,
    QLabel, 
    QLineEdit, 
    QPushButton, 
    QTextEdit, 
    QGridLayout, 
    QDialog,
    QFileDialog, 
    QMessageBox, 
    QListWidget, 
    QListView,
    QComboBox,
    QProxyStyle,
    QStyle,
    QScrollArea,
    QGroupBox,
    QFormLayout,
    QSpinBox,
    QCheckBox,
    QColorDialog
)
from PyQt6 import QtCore 
from PyQt6.QtGui import QColor, QShortcut, QKeySequence, QFont, QPen
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtCore import (
    Qt,
    qInstallMessageHandler
)
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter

import numpy as np
import sqlite3

from raman_dpid.utils import (
    find_spectrum_matches, 
    get_unique_mineral_combinations_optimized,
    get_xy_from_file, 
    deserialize, 
    baseline_als, 
    get_peaks, 
    get_crop_index_suggestion,
    gaussian
)

from raman_dpid.discretize import DraggableGraph, DraggableScatter
from raman_dpid.spectra import Spectrum
from raman_dpid.plots import CroppablePlotWidget
from raman_dpid.commands import (
    CommandHistory, 
    LoadSpectrumCommand, 
    PointDragCommand,
    CommandSpectrum, 
    EstimateBaselineCommand, 
    CorrectBaselineCommand,
    CropCommand,
    AddPeakPointCommand,
    RemovePeakPointCommand,
    SmoothCommand,
    FitPeaksCommand,
    FitPeaksCommand2
)

def custom_qt_message_handler(msg_type, context, message):
    if "skipping QEventPoint" in message:
        # Ignore this specific warning message
        return
    # For other messages, use the default handler (prints to the console)
    print(message)

class MouseMode(Enum):
    NORMAL = 1
    ADD_POINT = 2
    REM_POINT = 3


class CenteredComboBoxStyle(QProxyStyle):
    def drawControl(self, element, option, painter, widget):
        if element == QStyle.ControlElement.CE_ComboBoxLabel:
            # Center the text in the display area
            option.displayAlignment = Qt.AlignmentFlag.AlignCenter
        super().drawControl(element, option, painter, widget)


class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        qInstallMessageHandler(custom_qt_message_handler)
        self.title = 'Raman Spectra Analyzer'
        self.database_path = None
        self.baseline_data = None
        self.baseline_plot = None
        self.loaded_spectrum = None
        self.spectrum = None
        self.cropping = False
        self.crop_region = None
        self.mouse_mode = MouseMode.NORMAL
        self.fit = None
        self.fit_stats = None
        self.fit_stats_2 = None
        self.fit_trace = None
        self.fit_component_traces = []
        self.gaussians = []
        self.gaussian_sum = None

        self.peaks_x = np.array([])
        self.peaks_y = np.array([])
        self.spectrum_plot = None
        
        self.peak_line = None
        self.center_line = None
        self.sigma_line = None

        self.updating_lines = False

        # Default styles
        self.gaussian_sum_pen = pg.mkPen('m', width=2)
        self.gaussian_pen = pg.mkPen('g', width=2, style=QtCore.Qt.PenStyle.DashLine)
        self.spectrum_pen = pg.mkPen('w', width=1)
        self.background_color = QColor('w')
        self.show_peak_points = True
        self.show_peak_labels = False
        self.peak_label_font_size = 10
        self.axis_label_font_size = 12
        self.axis_label_color = QColor('k')
        self.tick_marks_x = True
        self.tick_marks_y = True
        self.tick_marks_inside = True
        self.tick_interval_x = None
        self.tick_interval_y = None

        # TODO gracefully handle missing config file
        with open(Path(__file__).parent / 'config.json', 'r') as f:
            self.config = json.load(f)
        self.init_UI()
        self.setup_connections()
        current_size = self.size()
        self.resize(current_size.width() + 1, current_size.height())
        self.resize(current_size.width(), current_size.height())
        self.init_keyboard_shortcuts()
        self.command_history = CommandHistory()

        self.batch_processing_steps = [
            'Load file',
            'Enter crop mode',
            'Apply crop',
            'Estimate baseline',
            'Apply baseline correction',
            'Smooth spectrum',
            'Find peaks',
            'Fit peaks',
            'Save spectrum',
            'Save fits',
            'Save plot as PNG'
        ]
        self.current_batch_file_index = 0
        self.current_batch_step_index = 0
        self.batch_files = []
        self.folder_path = ''

        self.init_config_model()

    def setup_connections(self):
        self.plot1.point_added.connect(self.on_point_added)
        self.plot1.point_removed.connect(self.on_point_removed)

    def resizeEvent(self, event):
        """Somewhat hacky but functional fix to the plot1.width != plot2.width problem"""
        # Let the resizing occur
        QApplication.processEvents()

        # Get the maximum width of the two plot widgets
        max_width = max(self.plot1.width(), self.plot2.width())

        # Set both plot widgets to have that max width as their minimum width
        self.plot1.setMinimumWidth(max_width)
        self.plot2.setMinimumWidth(max_width)

        # Additionally, set their size policy to be Preferred for width, so they try to maintain this width
        policy1 = self.plot1.sizePolicy()
        policy1.setHorizontalPolicy(QSizePolicy.Policy.Preferred)
        policy1.setVerticalPolicy(QSizePolicy.Policy.Preferred)
        self.plot1.setSizePolicy(policy1)

        policy2 = self.plot2.sizePolicy()
        policy2.setHorizontalPolicy(QSizePolicy.Policy.Preferred)
        policy2.setVerticalPolicy(QSizePolicy.Policy.Preferred)
        self.plot2.setSizePolicy(policy2)

        # Make sure to call the base class' method to ensure the event is handled properly
        super().resizeEvent(event)

    def show_whats_new(self):
        # Load the new features from whats_new.py
        try:
            from whats_new import new_features, WhatsNewDialog
            platform_key = 'nt' if os.name == 'nt' else 'posix'
            messages = new_features.get(platform_key, [])

            # Display the custom dialog
            dialog = WhatsNewDialog(messages, self)
            response = dialog.exec()
            
            # If the dialog was closed after viewing all messages, set show_whats_new to False
            if response == QDialog.DialogCode.Accepted and dialog.current_index == len(messages) - 1:
                self.config['show_whats_new'] = False
                with open(Path(__file__).parent / 'config.json', 'w') as f:
                    json.dump(self.config, f, indent=4)

        except ImportError:
            pass  # If whats_new.py is not found, just skip showing the messages

    def init_keyboard_shortcuts(self):
        undo_shortcut = QShortcut(QKeySequence('Ctrl+Z'), self)
        undo_shortcut.activated.connect(self.undo)

        redo_shortcut = QShortcut(QKeySequence('Ctrl+Shift+Z'), self)
        redo_shortcut.activated.connect(self.redo)

        load_spectrum_shortcut = QShortcut(QKeySequence('Ctrl+L'), self)
        load_spectrum_shortcut.activated.connect(self.load_unknown_spectrum)

        crop_shortcut = QShortcut(QKeySequence('Ctrl+R'), self)
        crop_shortcut.activated.connect(self.toggle_crop_mode)

        baseline_shortcut = QShortcut(QKeySequence('Ctrl+E'), self)
        baseline_shortcut.activated.connect(self.baseline_callback)

        discretize_shortcut = QShortcut(QKeySequence('Ctrl+D'), self)
        discretize_shortcut.activated.connect(self.discretize_baseline)

        save_shortcut = QShortcut(QKeySequence('Ctrl+S'), self)
        save_shortcut.activated.connect(self.save_edited_spectrum)
        
    def undo(self):
        self.command_history.undo()
    
    def redo(self):
        self.command_history.redo()

    def init_UI(self):
        """Initialization method for the User Interface
        main_layout
          |--search_layout
          |    |--database_layout
          |    |--peaks_layout
          |    |--tolerance_layout
          |--results_layout
          |--plot1_layout
          |--plot2_layout
        """

        # Set up container for overall layout
        self.main_widget = QWidget(self)
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create a QScrollArea
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)

        # DATABASE & SEARCH AREA
        search_layout = QHBoxLayout()
        search_widget = QWidget()
        search_widget.setLayout(search_layout)

        # Database selection
        database_layout = QHBoxLayout()
        database_widget = QWidget()
        database_widget.setLayout(database_layout)
        self.database_label = QLabel("Database: None selected", self)
        self.load_database_button = QPushButton('Load Database', self)
        self.load_database_button.clicked.connect(self.load_database_file)
        database_layout.addWidget(self.database_label)
        database_layout.addWidget(self.load_database_button)
        search_layout.addWidget(database_widget)
        
        # Peaks entry 
        peaks_layout = QHBoxLayout()
        peaks_widget = QWidget()
        peaks_widget.setLayout(peaks_layout)
        self.label_peaks = QLabel("Peaks (comma-separated):", self)
        self.textbox_peaks = QLineEdit(self)
        self.textbox_peaks.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        peaks_layout.addWidget(self.label_peaks)
        peaks_layout.addWidget(self.textbox_peaks)
        search_layout.addWidget(peaks_widget)

        # Tolerance Entry
        tolerance_layout = QHBoxLayout()
        tolerance_widget = QWidget()
        tolerance_widget.setLayout(tolerance_layout)
        self.label_tolerance = QLabel("Tolerance:", self)
        self.textbox_tolerance = QLineEdit(self)
        self.textbox_tolerance.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        tolerance_layout.addWidget(self.label_tolerance)
        tolerance_layout.addWidget(self.textbox_tolerance)
        search_layout.addWidget(tolerance_widget)

        # Search Button
        self.button_search = QPushButton('Search', self)
        self.button_search.clicked.connect(self.on_search)
        search_layout.addWidget(self.button_search)

        main_layout.addWidget(search_widget)

        # RESULTS AREA
        results_layout = QHBoxLayout()
        results_widget = QWidget()
        results_widget.setLayout(results_layout)
        self.result_single = QTextEdit(self)
        self.result_double = QTextEdit(self)
        self.result_triple = QTextEdit(self)
        self.result_single.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.result_double.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.result_triple.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        results_layout.addWidget(self.result_single)
        results_layout.addWidget(self.result_double)
        results_layout.addWidget(self.result_triple)
        main_layout.addWidget(results_widget)

        # ADD A THIN LINE HERE

        # LOADED SPECTRUM GRAPH AND UTILITIES
        plot1_layout = QGridLayout()
        plot1_widget = QWidget()
        plot1_widget.setLayout(plot1_layout)
        plot1_layout.setColumnStretch(0, 1) # TODO align more precisely
        plot1_buttons_layout = QVBoxLayout()
        plot1_buttons_widget = QWidget()
        plot1_buttons_widget.setLayout(plot1_buttons_layout)
        plot1_layout.addWidget(plot1_buttons_widget, 0, 2, 1, 1)
        main_layout.addWidget(plot1_widget)
        
        # PlotWidget: Plot 1
        self.plot1 = CroppablePlotWidget(self)
        self.plot1.setLabel('left', 'Intensity', units='w<sub>n</sub>')#, unitPrefix='k')
        self.plot1.setLabel('bottom', 'Raman Shift', units='cm<sup>-1</sup>')
        self.plot1.getPlotItem().getAxis('bottom').autoSIPrefix = False
        self.plot1.getPlotItem().getAxis('left').autoSIPrefix = True
        plot1_layout.addWidget(self.plot1, 0, 0, 1, 2)

        # Button: load spectrum
        self.button_load_file = QPushButton('Load File', self)
        self.button_load_file.clicked.connect(self.load_unknown_spectrum)
        plot1_buttons_layout.addWidget(self.button_load_file)

        # Button: estimate / correct baseline
        self.button_baseline = QPushButton('Estimate Baseline', self)
        self.button_baseline.clicked.connect(self.baseline_callback)
        plot1_buttons_layout.addWidget(self.button_baseline)

        # LineEdit: enter value for baseline ALS
        self.lineedit_lambda = QLineEdit(self)
        self.lineedit_lambda.setPlaceholderText('lambda (default: 100000)')
        plot1_buttons_layout.addWidget(self.lineedit_lambda)

        # Button: discretize baseline
        self.button_discretize = QPushButton('Discretize Baseline', self)
        self.button_discretize.clicked.connect(self.discretize_baseline)
        plot1_buttons_layout.addWidget(self.button_discretize)

        # Button: suggest crop
        self.suggest_crop_button = QPushButton("Suggest Crop", self)
        self.suggest_crop_button.clicked.connect(self.suggest_crop)
        plot1_buttons_layout.addWidget(self.suggest_crop_button)

        # Button: crop
        self.crop_button = QPushButton("Enter Crop Mode", self)
        self.crop_button.clicked.connect(self.toggle_crop_mode)
        plot1_buttons_layout.addWidget(self.crop_button)

        # Button: save spectrum
        self.button_save_spectrum = QPushButton('Save Spectrum', self)
        self.button_save_spectrum.clicked.connect(self.save_edited_spectrum)
        plot1_buttons_layout.addWidget(self.button_save_spectrum)

        # Button: smooth spectrum
        self.button_smooth_spectrum = QPushButton('Smooth Spectrum', self)
        self.button_smooth_spectrum.clicked.connect(self.smooth_spectrum)
        plot1_buttons_layout.addWidget(self.button_smooth_spectrum)

        # Button: fit peaks
        self.button_fit_peaks = QPushButton('Fit Peaks (Gauss)', self)
        self.button_fit_peaks.clicked.connect(self.fit_peaks)
        plot1_buttons_layout.addWidget(self.button_fit_peaks)

        # Dropdown: change mousemode
        self.dropdown_change_mousemode = QComboBox(self)
        self.dropdown_change_mousemode.addItems(['Mouse Mode: Normal', 'Mouse Mode: Add Peak', 'Mouse Mode: Remove Peak'])
        self.dropdown_change_mousemode.currentIndexChanged.connect(self.change_mouse_mode)
        plot1_buttons_layout.addWidget(self.dropdown_change_mousemode)

        # Dropdown: edit peaks
        self.dropdown_edit_peak = QComboBox(self)
        self.dropdown_edit_peak.addItems(['Edit Peak: None Selected'])
        self.dropdown_edit_peak.currentIndexChanged.connect(self.update_control_lines)
        self.dropdown_edit_peak.setEnabled(False)
        plot1_buttons_layout.addWidget(self.dropdown_edit_peak)

        # Button: print fits
        self.button_print_fits = QPushButton('Save Fits and Write PNG', self)
        self.button_print_fits.clicked.connect(self.print_fit_stats)
        plot1_buttons_layout.addWidget(self.button_print_fits)

        # Button: Toggle Config Panel
        self.toggle_config_panel_button = QPushButton('Show Config Panel', self)
        self.toggle_config_panel_button.clicked.connect(self.toggle_config_panel)
        plot1_buttons_layout.addWidget(self.toggle_config_panel_button)

        # Button: Toggle Batch Processing Window
        self.toggle_batch_processing_button = QPushButton('Show Batch Processing Window', self)
        self.toggle_batch_processing_button.clicked.connect(self.toggle_batch_processing_window)
        plot1_buttons_layout.addWidget(self.toggle_batch_processing_button)

        # Config Panel (initially hidden)
        self.config_panel = QDialog()
        self.config_panel.setVisible(False)
        self.config_panel.finished.connect(self.on_config_dialog_close)
        self.init_config_panel()

        # Batch Processing Window (initially hidden)
        self.batch_processing_window = QDialog()
        self.batch_processing_window.setVisible(False)
        self.batch_processing_window.finished.connect(self.on_batch_processing_window_close)
        self.init_batch_processing_window()

        # LineEdits: scipy.signal.find_peaks() parameters
        plot1_peak_params_layout = QGridLayout()
        plot1_peak_params_widget = QWidget()
        plot1_peak_params_widget.setLayout(plot1_peak_params_layout)
        plot1_buttons_layout.addWidget(plot1_peak_params_widget)

        # LineEdit: width
        self.textbox_width = QLineEdit(self)
        self.textbox_width.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.textbox_width.setPlaceholderText('`width`')
        plot1_peak_params_layout.addWidget(self.textbox_width, 0, 0)

        # LineEdit: rel_height
        self.textbox_rel_height = QLineEdit(self)
        self.textbox_rel_height.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.textbox_rel_height.setPlaceholderText('`rel_height`')
        plot1_peak_params_layout.addWidget(self.textbox_rel_height, 0, 1)

        # LineEdit: height
        self.textbox_height = QLineEdit(self)
        self.textbox_height.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.textbox_height.setPlaceholderText('`height`')
        plot1_peak_params_layout.addWidget(self.textbox_height, 1, 0)

        # LineEdit: prominence
        self.textbox_prominence = QLineEdit(self)
        self.textbox_prominence.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.textbox_prominence.setPlaceholderText('`prominence`')
        plot1_peak_params_layout.addWidget(self.textbox_prominence, 1, 1)

        # Button: Find peaks
        plot1_peaks_buttons_layout = QHBoxLayout()
        plot1_peaks_buttons_widget = QWidget()
        plot1_peaks_buttons_widget.setLayout(plot1_peaks_buttons_layout)
        plot1_buttons_layout.addWidget(plot1_peaks_buttons_widget)

        self.button_find_peaks = QPushButton('Find Peaks', self)
        self.button_find_peaks.clicked.connect(self.find_peaks)
        #plot1_buttons_layout.addWidget(self.button_find_peaks)
        plot1_peaks_buttons_layout.addWidget(self.button_find_peaks)

        # Button: Show peak positions
        self.button_show_peak_labels = QPushButton('Show Labels', self)
        self.button_show_peak_labels.clicked.connect(self.toggle_labels_callback)
        plot1_peaks_buttons_layout.addWidget(self.button_show_peak_labels)

        # ListWidget: Log for Plot 1
        self.plot1_log = QListWidget()
        plot1_buttons_layout.addWidget(self.plot1_log)

        # ADD A THIN LINE

        # DATABASE SPECTRA GRAPH AND UTILITIES
        plot2_layout = QGridLayout()
        plot2_widget = QWidget()
        plot2_widget.setLayout(plot2_layout)
        plot2_layout.setColumnStretch(0, 1)
        main_layout.addWidget(plot2_widget)
        plot2_buttons_layout = QVBoxLayout()
        plot2_buttons_widget = QWidget()
        plot2_buttons_widget.setLayout(plot2_buttons_layout)
        plot2_layout.addWidget(plot2_buttons_widget, 0, 2, 1, 1)

        # PlotWidget: Plot 2
        self.plot2 = pg.PlotWidget(self)
        self.plot2.setLabel('left', 'Intensity', units='w<sub>n</sub>', unitPrefix='k')
        self.plot2.setLabel('bottom', 'Raman Shift', units='cm<sup>-1</sup>')
        self.plot2.getPlotItem().getAxis('bottom').autoSIPrefix = False
        self.plot2.getPlotItem().getAxis('left').autoSIPrefix = True
        plot2_layout.addWidget(self.plot2, 0, 0, 1, 2)
        
        # LineEdit: mineral name
        # TODO add auto-fill from database here
        self.mineral_input = QLineEdit(self)
        self.mineral_input.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.mineral_input.setPlaceholderText("Enter Mineral Name")
        plot2_buttons_layout.addWidget(self.mineral_input)

        # LineEdit: wavelength
        self.wavelength_input = QLineEdit(self)
        self.wavelength_input.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.wavelength_input.setPlaceholderText("Enter Wavelength")
        plot2_buttons_layout.addWidget(self.wavelength_input)

        # Button: search database
        self.search_button = QPushButton('Search', self)
        self.search_button.clicked.connect(self.search_database)
        plot2_buttons_layout.addWidget(self.search_button)

        # Button: plot selected spectra
        self.plot_button = QPushButton('Plot', self)
        self.plot_button.clicked.connect(self.plot_selected_spectra)
        plot2_buttons_layout.addWidget(self.plot_button)

        # Button: Align axes with above graph
        self.align_button = QPushButton('Align X Axis', self)
        self.align_button.clicked.connect(self.match_range)
        plot2_buttons_layout.addWidget(self.align_button)

        # ListWidget: results from searching database
        self.results_list = QListWidget(self)
        self.results_list.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
        plot2_buttons_layout.addWidget(self.results_list)

        scroll_area.setWidget(self.main_widget)

        # Create a new central widget to hold the scroll area
        central_widget = QWidget(self)
        central_layout = QVBoxLayout(central_widget)
        central_layout.addWidget(scroll_area)

        # Set the central widget to the scroll area container
        self.setCentralWidget(central_widget)
        
        # Setting central widget and layout
        self.setWindowTitle(self.title)

    def init_batch_processing_window(self):
        # Create the layout
        batch_layout = QVBoxLayout()

        # First row: Select Folder button and label
        folder_layout = QHBoxLayout()
        self.select_folder_button = QPushButton('Select Folder', self)
        self.select_folder_button.clicked.connect(self.select_folder)
        self.folder_label = QLabel('No folder selected', self)
        folder_layout.addWidget(self.select_folder_button)
        folder_layout.addWidget(self.folder_label)
        batch_layout.addLayout(folder_layout)

        # Second row: Current file label and filename
        current_file_layout = QHBoxLayout()
        self.current_file_label = QLabel('Current file:', self)
        self.current_file_name_label = QLabel('No file selected', self)
        current_file_layout.addWidget(self.current_file_label)
        current_file_layout.addWidget(self.current_file_name_label)
        batch_layout.addLayout(current_file_layout)

        # Third row: Next button and next action label
        next_layout = QHBoxLayout()
        self.next_button = QPushButton('Next:', self)
        self.next_button.clicked.connect(self.batch_next_step)
        self.next_action_label = QLabel('Load file', self)
        next_layout.addWidget(self.next_button)
        next_layout.addWidget(self.next_action_label)
        batch_layout.addLayout(next_layout)

        self.batch_processing_window.setLayout(batch_layout)

    def toggle_batch_processing_window(self):
        if self.batch_processing_window.isVisible():
            self.batch_processing_window.setVisible(False)
            self.toggle_batch_processing_button.setText('Show Batch Processing Window')
        else:
            self.batch_processing_window.setVisible(True)
            self.toggle_batch_processing_button.setText('Hide Batch Processing Window')

    def on_batch_processing_window_close(self):
        if not self.batch_processing_window.isVisible():
            self.toggle_batch_processing_button.setText('Show Batch Processing Window')

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Folder')
        if folder:
            self.folder_path = folder
            self.folder_label.setText(folder)
            # Get the list of files in the folder
            self.batch_files = [os.path.join(folder, f) for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)) and (f.endswith('.txt') or f.endswith('.spc'))]
            self.current_batch_file_index = 0
            self.current_batch_step_index = 0
            if self.batch_files:
                first_file = self.batch_files[self.current_batch_file_index]
                self.next_action_label.setText(f'Load file {os.path.basename(first_file)}')
            else:
                self.next_action_label.setText('No files in folder')
        else:
            self.folder_label.setText('No folder selected')
            self.batch_files = []
            self.next_action_label.setText('')

    def batch_next_step(self):
        if not self.batch_files:
            QMessageBox.warning(self, 'No files', 'No files to process. Please select a folder with files.')
            return

        if self.current_batch_file_index >= len(self.batch_files):
            QMessageBox.information(self, 'Done', 'All files have been processed.')
            self.next_action_label.setText('All files processed')
            return

        current_file = self.batch_files[self.current_batch_file_index]
        current_step = self.batch_processing_steps[self.current_batch_step_index]

        if current_step == 'Load file':
            # Use existing file-loading logic
            self.unknown_spectrum_path = Path(current_file)
            command = LoadSpectrumCommand(self, *get_xy_from_file(self.unknown_spectrum_path))
            self.command_history.execute(command)
            self.current_file_name_label.setText(os.path.basename(current_file))
            self.plot1_log.addItem(f'Loaded file: {current_file}')

        elif current_step == 'Enter crop mode':
            if not self.cropping:
                self.toggle_crop_mode()

        elif current_step == 'Apply crop':
            if self.cropping:
                self.toggle_crop_mode()

        elif current_step == 'Estimate baseline':
            if self.button_baseline.text() == "Estimate Baseline":
                self.baseline_callback()

        elif current_step == 'Apply baseline correction':
            if self.button_baseline.text() == "Apply Baseline Correction":
                self.baseline_callback()

        elif current_step == 'Smooth spectrum':
            self.smooth_spectrum()

        elif current_step == 'Find peaks':
            self.find_peaks()

        elif current_step == 'Fit peaks':
            self.fit_peaks()

        elif current_step == 'Save spectrum':
            default_name = f"{self.unknown_spectrum_path.stem}_processed.txt"
            save_path = os.path.join(self.folder_path, default_name)
            with open(save_path, 'w') as f:
                for x, y in zip(self.spectrum.x, self.spectrum.y):
                    f.write(f"{x} {y}\n")
            self.plot1_log.addItem(f'Saved edited spectrum to: {save_path}')

        elif current_step == 'Save fits':
            fits_save_path = os.path.join(self.folder_path, f"{self.unknown_spectrum_path.stem}_fits.txt")
            with open(fits_save_path, 'w') as f:
                for peak, stats in self.fit_stats_2.items():
                    f.write(f"{peak}\n")
                    for key, val in stats.items():
                        if key in ['Center', 'Sigma', 'Height']:
                            f.write(f"{key}: {val}\n")
            self.plot1_log.addItem(f'Saved fits to: {fits_save_path}')

        elif current_step == 'Save plot as PNG':
            # Call the method to save the spectrum plot as PNG
            self.save_spectrum_as_png()

        # Move to the next step
        self.current_batch_step_index += 1

        if self.current_batch_step_index >= len(self.batch_processing_steps):
            # Reset step index, move to next file
            self.current_batch_step_index = 0
            self.current_batch_file_index += 1
            if self.current_batch_file_index >= len(self.batch_files):
                self.next_action_label.setText('All files processed')
                QMessageBox.information(self, 'Done', 'All files have been processed.')
                return
            else:
                next_file = self.batch_files[self.current_batch_file_index]
                self.next_action_label.setText(f'Load file {os.path.basename(next_file)}')
                self.current_file_name_label.setText('No file selected')
                self.plot1.clear()
        else:
            # Update next action label
            next_step = self.batch_processing_steps[self.current_batch_step_index]
            if next_step == 'Load file':
                next_file = self.batch_files[self.current_batch_file_index]
                self.next_action_label.setText(f'{next_step}: {os.path.basename(next_file)}')
            else:
                self.next_action_label.setText(next_step)


    def save_spectrum_as_png(self):
        if self.spectrum is None:
            QMessageBox.warning(self, 'No Spectrum', 'No spectrum loaded to save as PNG.')
            return

        # Construct the file path for saving
        default_name = f"{self.unknown_spectrum_path.stem}_spectrum.png"
        png_save_path = os.path.join(self.folder_path, default_name)
        
        # Use pyqtgraph's ImageExporter to export the plot as PNG
        exporter = ImageExporter(self.plot1.plotItem)
        
        # Set the export size (optional, you can remove this if you want to use the default size)
        exporter.parameters()['width'] = 10_000  # Adjust width as needed for higher resolution
        
        try:
            # Save the file
            exporter.export(png_save_path)
            self.plot1_log.addItem(f'Saved spectrum plot as PNG: {png_save_path}')
        except Exception as e:
            QMessageBox.critical(self, 'Error Saving PNG', f'Error occurred while saving PNG: {str(e)}')

    def init_config_model(self):
        # Initialize with some default colors
        self.gaussian_sum_color = QColor('magenta')
        self.gaussian_color = QColor('green')
        self.spectrum_color = QColor('white')
        self.background_color = QColor('black')

    def init_config_panel(self):
        """Initialize the configuration panel with all the controls"""

        # Create a widget that will hold all the controls (to be placed inside the QScrollArea)
        config_content = QWidget()
        config_layout = QVBoxLayout(config_content)

        # Gaussian Sum Style
        gaussian_sum_group = QGroupBox('Gaussian Sum Style')
        gaussian_sum_layout = QFormLayout()
        gaussian_sum_group.setLayout(gaussian_sum_layout)

        # Line Style
        self.gaussian_sum_line_style_combo = QComboBox()
        self.gaussian_sum_line_style_combo.addItems(['Solid', 'Dash', 'Dot', 'DashDot'])
        self.gaussian_sum_line_style_combo.currentIndexChanged.connect(self.update_gaussian_sum_style)
        gaussian_sum_layout.addRow('Line Style:', self.gaussian_sum_line_style_combo)

        # Line Thickness
        self.gaussian_sum_line_thickness_spinbox = QSpinBox()
        self.gaussian_sum_line_thickness_spinbox.setRange(1, 10)
        self.gaussian_sum_line_thickness_spinbox.setValue(2)
        self.gaussian_sum_line_thickness_spinbox.valueChanged.connect(self.update_gaussian_sum_style)
        gaussian_sum_layout.addRow('Thickness:', self.gaussian_sum_line_thickness_spinbox)

        # Line Color
        self.gaussian_sum_line_color_button = QPushButton()
        self.gaussian_sum_line_color_button.setStyleSheet("background-color: magenta")
        self.gaussian_sum_line_color_button.clicked.connect(self.select_gaussian_sum_color)
        gaussian_sum_layout.addRow('Color:', self.gaussian_sum_line_color_button)

        config_layout.addWidget(gaussian_sum_group)

        # Individual Gaussians Style
        gaussian_group = QGroupBox('Individual Gaussians Style')
        gaussian_layout = QFormLayout()
        gaussian_group.setLayout(gaussian_layout)

        # Line Style
        self.gaussian_line_style_combo = QComboBox()
        self.gaussian_line_style_combo.addItems(['Solid', 'Dash', 'Dot', 'DashDot'])
        self.gaussian_line_style_combo.currentIndexChanged.connect(self.update_gaussian_style)
        gaussian_layout.addRow('Line Style:', self.gaussian_line_style_combo)

        # Line Thickness
        self.gaussian_line_thickness_spinbox = QSpinBox()
        self.gaussian_line_thickness_spinbox.setRange(1, 10)
        self.gaussian_line_thickness_spinbox.setValue(2)
        self.gaussian_line_thickness_spinbox.valueChanged.connect(self.update_gaussian_style)
        gaussian_layout.addRow('Thickness:', self.gaussian_line_thickness_spinbox)

        # Line Color
        self.gaussian_line_color_button = QPushButton()
        self.gaussian_line_color_button.setStyleSheet("background-color: green")
        self.gaussian_line_color_button.clicked.connect(self.select_gaussian_color)
        gaussian_layout.addRow('Color:', self.gaussian_line_color_button)

        config_layout.addWidget(gaussian_group)

        # Spectrum Style
        spectrum_group = QGroupBox('Spectrum Style')
        spectrum_layout = QFormLayout()
        spectrum_group.setLayout(spectrum_layout)

        # Line Style
        self.spectrum_line_style_combo = QComboBox()
        self.spectrum_line_style_combo.addItems(['Solid', 'Dash', 'Dot', 'DashDot'])
        self.spectrum_line_style_combo.currentIndexChanged.connect(self.update_spectrum_style)
        spectrum_layout.addRow('Line Style:', self.spectrum_line_style_combo)

        # Line Thickness
        self.spectrum_line_thickness_spinbox = QSpinBox()
        self.spectrum_line_thickness_spinbox.setRange(1, 10)
        self.spectrum_line_thickness_spinbox.setValue(1)
        self.spectrum_line_thickness_spinbox.valueChanged.connect(self.update_spectrum_style)
        spectrum_layout.addRow('Thickness:', self.spectrum_line_thickness_spinbox)

        # Line Color
        self.spectrum_line_color_button = QPushButton()
        self.spectrum_line_color_button.setStyleSheet("background-color: white")
        self.spectrum_line_color_button.clicked.connect(self.select_spectrum_color)
        spectrum_layout.addRow('Color:', self.spectrum_line_color_button)

        config_layout.addWidget(spectrum_group)

        # Background Style
        background_group = QGroupBox('Background Style')
        background_layout = QFormLayout()
        background_group.setLayout(background_layout)
        self.background_color_button = QPushButton()
        self.background_color_button.setStyleSheet(f"background-color: {self.background_color.name()}")
        self.background_color_button.clicked.connect(self.select_background_color)
        background_layout.addRow('Color:', self.background_color_button)

        config_layout.addWidget(background_group)

        # Tick Marks
        tick_group = QGroupBox('Tick Marks')
        tick_layout = QFormLayout()
        tick_group.setLayout(tick_layout)

        # X-axis Tick Marks
        self.tick_marks_x_checkbox = QCheckBox('Show X-axis Tick Marks')
        self.tick_marks_x_checkbox.setChecked(True)
        self.tick_marks_x_checkbox.stateChanged.connect(self.update_tick_marks)
        tick_layout.addRow(self.tick_marks_x_checkbox)

        # Y-axis Tick Marks
        self.tick_marks_y_checkbox = QCheckBox('Show Y-axis Tick Marks')
        self.tick_marks_y_checkbox.setChecked(True)
        self.tick_marks_y_checkbox.stateChanged.connect(self.update_tick_marks)
        tick_layout.addRow(self.tick_marks_y_checkbox)

        # Tick Position
        self.tick_position_combo = QComboBox()
        self.tick_position_combo.addItems(['Inside', 'Outside'])
        self.tick_position_combo.currentIndexChanged.connect(self.update_tick_marks)
        tick_layout.addRow('Tick Position:', self.tick_position_combo)

        # Tick Width
        self.tick_width_spinbox = QSpinBox()
        self.tick_width_spinbox.setRange(1,10)
        self.tick_width_spinbox.setValue(1)
        self.tick_width_spinbox.valueChanged.connect(self.update_tick_marks)
        tick_layout.addRow('Tick Width:', self.tick_width_spinbox)

        # Tick Interval X
        self.tick_interval_x_spinbox = QSpinBox()
        self.tick_interval_x_spinbox.setRange(1, 1000)
        self.tick_interval_x_spinbox.setValue(0)  # 0 means auto
        self.tick_interval_x_spinbox.valueChanged.connect(self.update_tick_marks)
        self.tick_interval_x_spinbox.setEnabled(False)
        tick_layout.addRow('X-axis Tick Interval:', self.tick_interval_x_spinbox)

        # Tick Interval Y
        self.tick_interval_y_spinbox = QSpinBox()
        self.tick_interval_y_spinbox.setRange(1, 1000)
        self.tick_interval_y_spinbox.setValue(0)  # 0 means auto
        self.tick_interval_y_spinbox.valueChanged.connect(self.update_tick_marks)
        self.tick_interval_y_spinbox.setEnabled(False)
        tick_layout.addRow('Y-axis Tick Interval:', self.tick_interval_y_spinbox)

        config_layout.addWidget(tick_group)

        # Peak Points and Labels
        peaks_group = QGroupBox('Peaks Display')
        peaks_layout = QFormLayout()
        peaks_group.setLayout(peaks_layout)

        # Toggle Peak Points
        self.show_peak_points_checkbox = QCheckBox('Show Peak Points')
        self.show_peak_points_checkbox.setChecked(True)
        self.show_peak_points_checkbox.stateChanged.connect(self.update_peak_points_visibility)
        peaks_layout.addRow(self.show_peak_points_checkbox)

        # Toggle Peak Labels
        self.show_peak_labels_checkbox = QCheckBox('Show Peak Labels')
        self.show_peak_labels_checkbox.setChecked(False)
        self.show_peak_labels_checkbox.stateChanged.connect(self.update_peak_labels_visibility)
        peaks_layout.addRow(self.show_peak_labels_checkbox)

        # Peak Label Font Size
        self.peak_label_font_size_spinbox = QSpinBox()
        self.peak_label_font_size_spinbox.setRange(6, 24)
        self.peak_label_font_size_spinbox.setValue(10)
        self.peak_label_font_size_spinbox.valueChanged.connect(self.update_peak_labels_style)
        peaks_layout.addRow('Peak Label Font Size:', self.peak_label_font_size_spinbox)

        # Peak Label Color
        self.peak_label_color_button = QPushButton()
        self.peak_label_color_button.setStyleSheet("background-color: red")
        self.peak_label_color_button.clicked.connect(self.select_peak_label_color)
        peaks_layout.addRow('Peak Label Color:', self.peak_label_color_button)

        config_layout.addWidget(peaks_group)

        # Axis Labels
        axis_group = QGroupBox('Axis Labels')
        axis_layout = QFormLayout()
        axis_group.setLayout(axis_layout)

        # Axis Label Font Size
        self.axis_label_font_size_spinbox = QSpinBox()
        self.axis_label_font_size_spinbox.setRange(6, 24)
        self.axis_label_font_size_spinbox.setValue(12)
        self.axis_label_font_size_spinbox.valueChanged.connect(self.update_axis_labels_style)
        axis_layout.addRow('Axis Label Font Size:', self.axis_label_font_size_spinbox)

        # Axis Label Color
        self.axis_label_color_button = QPushButton()
        self.axis_label_color_button.setStyleSheet("background-color: black")
        self.axis_label_color_button.clicked.connect(self.select_axis_label_color)
        axis_layout.addRow('Axis Label Color:', self.axis_label_color_button)

        config_layout.addWidget(axis_group)


        # Create the scroll area and set it to hold the config_content widget
        scroll_area = QScrollArea(self.config_panel)
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(config_content)  # Set the content widget in the scroll area

        # Set the scroll area as the central layout of the config panel (QDialog)
        layout = QVBoxLayout(self.config_panel)
        layout.addWidget(scroll_area)


    def toggle_config_panel(self):
        if self.config_panel.isVisible():
            self.config_panel.setVisible(False)
            self.toggle_config_panel_button.setText('Show Config Panel')
        else:
            self.config_panel.setVisible(True)
            self.toggle_config_panel_button.setText('Hide Config Panel')

    def on_config_dialog_close(self):
        if not self.config_panel.isVisible():
            self.toggle_config_panel_button.setText('Show Config Panel')

    def select_gaussian_sum_color(self):
        color = QColorDialog.getColor(self.gaussian_sum_color, self, 'Select Gaussian Sum Color')
        if color.isValid():
            self.gaussian_sum_line_color_button.setStyleSheet(f"background-color: {color.name()}")
            self.gaussian_sum_color = color
            self.gaussian_sum_pen.setColor(color)
            self.update_gaussian_sum_style()

    def update_gaussian_sum_style(self):
        style = self.gaussian_sum_line_style_combo.currentText()
        thickness = self.gaussian_sum_line_thickness_spinbox.value()
        color = self.gaussian_sum_pen.color()

        pen_style = self.get_pen_style(style)
        self.gaussian_sum_pen = pg.mkPen(color=color, width=thickness, style=pen_style)

        if self.gaussian_sum:
            self.gaussian_sum.setPen(self.gaussian_sum_pen)

    def select_gaussian_color(self):
        color = QColorDialog.getColor(self.gaussian_color, self, 'Select Gaussian Color')
        if color.isValid():
            self.gaussian_line_color_button.setStyleSheet(f"background-color: {color.name()}")
            self.gaussian_color = color
            self.gaussian_pen.setColor(color)
            self.update_gaussian_style()

    def update_gaussian_style(self):
        style = self.gaussian_line_style_combo.currentText()
        thickness = self.gaussian_line_thickness_spinbox.value()
        color = self.gaussian_pen.color()

        pen_style = self.get_pen_style(style)
        self.gaussian_pen = pg.mkPen(color=color, width=thickness, style=pen_style)

        for gaussian_curve in self.gaussians:
            gaussian_curve.setPen(self.gaussian_pen)

    def select_spectrum_color(self):
        color = QColorDialog.getColor(self.spectrum_color, self, 'Select Spectrum Color')
        if color.isValid():
            self.spectrum_line_color_button.setStyleSheet(f"background-color: {color.name()}")
            self.spectrum_color = color
            self.spectrum_pen.setColor(color)
            self.update_spectrum_style()

    def update_spectrum_style(self):
        style = self.spectrum_line_style_combo.currentText()
        thickness = self.spectrum_line_thickness_spinbox.value()
        color = self.spectrum_pen.color()

        pen_style = self.get_pen_style(style)
        self.spectrum_pen = pg.mkPen(color=color, width=thickness, style=pen_style)

        # Update the spectrum plot
        if hasattr(self, 'spectrum_plot'):
            self.spectrum_plot.setPen(self.spectrum_pen)

    def select_background_color(self):
        color = QColorDialog.getColor(self.background_color, self, 'Select Background Color')
        if color.isValid():
            self.background_color_button.setStyleSheet(f"background-color: {color.name()}")
            self.background_color = color
            self.plot1.setBackground(self.background_color)

    # def update_tick_marks(self):
    #     x_ticks = self.tick_marks_x_checkbox.isChecked()
    #     y_ticks = self.tick_marks_y_checkbox.isChecked()
    #     tick_position = self.tick_position_combo.currentText()
    #     x_interval = self.tick_interval_x_spinbox.value()
    #     y_interval = self.tick_interval_y_spinbox.value()
    #     tick_width = self.tick_width_spinbox.value()

    #     # Update X-axis
    #     x_axis = self.plot1.getAxis('bottom')
    #     x_axis.setTicks([] if not x_ticks else None)
    #     x_axis.setStyle(showValues=x_ticks)
    #     x_axis.setTickSpacing(levels=[(x_interval, 0)] if x_interval > 0 else None)
    #     x_axis.setStyle(tickLength=-5 if tick_position == 'Inside' else 5)

    #     # Update Y-axis
    #     y_axis = self.plot1.getAxis('left')
    #     y_axis.setTicks([] if not y_ticks else None)
    #     y_axis.setStyle(showValues=y_ticks)
    #     y_axis.setTickSpacing(levels=[(y_interval, 0)] if y_interval > 0 else None)
    #     y_axis.setStyle(tickLength=-5 if tick_position == 'Inside' else 5)

    #     self.plot1.replot()

    def update_tick_marks(self):
        x_ticks = self.tick_marks_x_checkbox.isChecked()
        y_ticks = self.tick_marks_y_checkbox.isChecked()
        tick_position = self.tick_position_combo.currentText()
        x_interval = self.tick_interval_x_spinbox.value()
        y_interval = self.tick_interval_y_spinbox.value()
        tick_width = self.tick_width_spinbox.value()

        # Update X-axis
        x_axis = self.plot1.getAxis('bottom')

        # Get current pen, modify its width, and apply it back
        current_x_pen = x_axis.pen()
        new_x_pen = QPen(current_x_pen.color(), tick_width, current_x_pen.style())
        x_axis.setTickPen(new_x_pen)

        x_axis.setTicks([] if not x_ticks else None)
        x_axis.setStyle(showValues=x_ticks)
        #x_axis.setTickSpacing(levels=[(x_interval, 0)] if x_interval > 0 else None)
        x_axis.setStyle(tickLength=-5 if tick_position == 'Inside' else 5)

        # Update Y-axis
        y_axis = self.plot1.getAxis('left')

        # Get current pen, modify its width, and apply it back
        current_y_pen = y_axis.pen()
        new_y_pen = QPen(current_y_pen.color(), tick_width, current_y_pen.style())
        y_axis.setTickPen(new_y_pen)

        y_axis.setTicks([] if not y_ticks else None)
        y_axis.setStyle(showValues=y_ticks)
        #y_axis.setTickSpacing(levels=[(y_interval, 0)] if y_interval > 0 else None)
        y_axis.setStyle(tickLength=-5 if tick_position == 'Inside' else 5)

        # Force the plot to re-render
        self.plot1.replot()

    def update_peak_points_visibility(self):
        self.show_peak_points = self.show_peak_points_checkbox.isChecked()
        self.refresh_peaks_view()

    def update_peak_labels_visibility(self):
        self.show_peak_labels = self.show_peak_labels_checkbox.isChecked()
        if self.show_peak_labels:
            self.add_peak_labels()
        else:
            self.remove_peak_labels()

    def update_peak_labels_style(self):
        self.peak_label_font_size = self.peak_label_font_size_spinbox.value()
        if self.show_peak_labels:
            self.remove_peak_labels()
            self.add_peak_labels()

    def select_peak_label_color(self):
        color = QColorDialog.getColor(self.peak_label_color, self, 'Select Peak Label Color')
        if color.isValid():
            self.peak_label_color_button.setStyleSheet(f"background-color: {color.name()}")
            self.peak_label_color = color
            if self.show_peak_labels:
                self.remove_peak_labels()
                self.add_peak_labels()

    def update_axis_labels_style(self):
        self.axis_label_font_size = self.axis_label_font_size_spinbox.value()
        font = QFont()
        font.setPointSize(self.axis_label_font_size)
        color = self.axis_label_color.name()
        tick_width = self.tick_width_spinbox.value()

        # Update axis labels
        self.plot1.getAxis('bottom').setStyle(tickFont=font)
        self.plot1.getAxis('bottom').setPen(pg.mkPen(color))
        self.plot1.getAxis('bottom').setTextPen(pg.mkPen(color))
        #self.plot1.getAxis('bottom').setTickPen(pg.mkPen(color))
        self.plot1.getAxis('left').setStyle(tickFont=font)
        self.plot1.getAxis('left').setPen(pg.mkPen(color))
        self.plot1.getAxis('left').setTextPen(pg.mkPen(color))
        #self.plot1.getAxis('left').setTickPen(pg.mkPen(color))

        x_axis = self.plot1.getAxis('bottom')
        y_axis = self.plot1.getAxis('left')

        # Get current pen, modify its width, and apply it back
        current_x_pen = x_axis.pen()
        new_x_pen = QPen(self.axis_label_color, tick_width, current_x_pen.style())
        x_axis.setTickPen(new_x_pen)

        # Get current pen, modify its width, and apply it back
        current_y_pen = y_axis.pen()
        new_y_pen = QPen(self.axis_label_color, tick_width, current_y_pen.style())
        y_axis.setTickPen(new_y_pen)

        self.plot1.replot()

    def select_axis_label_color(self):
        color = QColorDialog.getColor(self.axis_label_color, self, 'Select Axis Label Color')
        if color.isValid():
            self.axis_label_color_button.setStyleSheet(f"background-color: {color.name()}")
            self.axis_label_color = color
            self.update_axis_labels_style()

    def get_pen_style(self, style_str):
        if style_str == 'Solid':
            return QtCore.Qt.PenStyle.SolidLine
        elif style_str == 'Dash':
            return QtCore.Qt.PenStyle.DashLine
        elif style_str == 'Dot':
            return QtCore.Qt.PenStyle.DotLine
        elif style_str == 'DashDot':
            return QtCore.Qt.PenStyle.DashDotLine
        else:
            return QtCore.Qt.PenStyle.SolidLine
    
    def print_fit_stats(self):
        if self.fit_stats_2 is not None:
            for peak, stats in self.fit_stats_2.items():
                print(peak)
                for key, val in stats.items():
                    if key in ['Center', 'Sigma', 'Height']:
                        print(f'\t{key}: {val}')

            # Save the fits to a file
            fits_save_path = os.path.join(self.folder_path, f"{self.unknown_spectrum_path.stem}_fits.txt")
            with open(fits_save_path, 'w') as f:
                for peak, stats in self.fit_stats_2.items():
                    f.write(f"{peak}\n")
                    for key, val in stats.items():
                        if key in ['Center', 'Sigma', 'Height']:
                            f.write(f"{key}: {val}\n")
            self.plot1_log.addItem(f'Saved fits to: {fits_save_path}')

            # Save PNG
            self.save_spectrum_as_png()


    def change_mouse_mode(self):
        current = self.dropdown_change_mousemode.currentText()
        if 'Normal' in current:
            self.mouse_mode = MouseMode.NORMAL
            self.plot1.mode = 'normal'
        elif 'Add' in current:
            self.mouse_mode = MouseMode.ADD_POINT
            self.plot1.mode = 'add'
        elif 'Remove' in current:
            self.mouse_mode = MouseMode.REM_POINT
            self.plot1.mode = 'delete'
        else:
            raise ValueError('Invalid mouse mode selected (somehow!)')

    def toggle_crop_mode(self):
        if self.cropping:
            self.crop_region = self.plot1.get_crop_region()
            self.apply_crop()
            self.crop_button.setText("Enter Crop Mode")
            self.cropping = False
            self.plot1.cropping = self.cropping
            if self.crop_region:
                self.plot1.removeItem(self.crop_region)
                self.crop_region = None
        else:
            self.crop_button.setText("Apply Crop")
            self.cropping = True
            self.plot1.cropping = self.cropping

    def save_edited_spectrum(self):
        default_name = f"{self.unknown_spectrum_path.stem}_processed.txt"
        suggested_path = self.unknown_spectrum_path.parent / default_name
        #options = QFileDialog.Option()
        fname, _ = QFileDialog.getSaveFileName(self, "Save Spectrum", filter="Text Files (*.txt);;All Files (*)")

        if fname:  # Check if user didn't cancel the dialog
            with open(fname, 'w') as f:
                for x, y in zip(self.spectrum.x, self.spectrum.y):
                    f.write(f"{x} {y}\n")
            
            self.plot1_log.addItem(f'Saved edited spectrum to: {fname}')

    def apply_crop(self):
        # If there's no crop_region, do nothing.
        if self.crop_region is None:
            return
        
        crop_start_x, crop_end_x = self.crop_region.getRegion()
        
        command = CropCommand(self, crop_start_x, crop_end_x)
        self.command_history.execute(command)

        # Remove the crop_region item from the plot.
        self.plot1.removeItem(self.crop_region)
        self.crop_region = None
        self.plot1.crop_region = None


    def smooth_spectrum(self):
        command = SmoothCommand(self)
        self.command_history.execute(command)

    def update_discretized_baseline(self):
        """Updates the baseline data of the loaded spectrum whenever user moves a point after discretization"""
        self.draggableGraph.setData(pos=np.array(list(zip(self.draggableScatter.data['x'], self.draggableScatter.data['y']))))
        self.baseline_data = np.interp(self.spectrum.x, self.draggableScatter.data['x'], self.draggableScatter.data['y'])
        if hasattr(self, 'interpolated_baseline'):
            self.plot1.removeItem(self.interpolated_baseline)
        self.interpolated_baseline = self.plot1.plot(self.spectrum.x, self.baseline_data, pen='g')

    def discretize_baseline(self):
        # Discretizing the baseline
        x_vals = np.arange(self.spectrum.x[0], self.spectrum.x[-1], self.config['discrete baseline step size'])
        y_vals = np.interp(x_vals, self.spectrum.x, self.baseline_data)

        # Clear the previous discretized baseline if it exists
        if hasattr(self, 'draggableScatter'):
            self.plot1.removeItem(self.draggableScatter)
        if hasattr(self, 'draggableGraph'):
            self.plot1.removeItem(self.draggableGraph)

        # TODO fix color not working... not sure if we need to set bursh or color or symbolBrush or pen or what...
        self.draggableScatter = DraggableScatter(x=x_vals, y=y_vals, size=self.config['discrete baseline point size'], symbolBrush=eval(self.config['discrete baseline point color']))
        self.draggableScatter.pointDragged.connect(self.update_discretized_baseline)
        self.draggableScatter.dragFinished.connect(self.handle_drag_finished)
        self.draggableGraph = DraggableGraph(scatter_data={'x': x_vals, 'y': y_vals})
        
        self.plot1.addItem(self.draggableGraph)
        self.plot1.addItem(self.draggableScatter)

        # Replace the smooth baseline with the discretized one
        self.plot1.removeItem(self.baseline_plot)

    def handle_drag_finished(self, index, startX, startY, endX, endY):
        command = PointDragCommand(self, index, startX, startY, endX, endY)
        self.command_history.execute(command)

    def match_range(self):
        name = self.align_button.text()
        if name == 'Align X Axis':
            if self.spectrum.x is not None:
                # left_margin = 80  # Adjust this value based on your needs
                # self.plot1.getPlotItem().setContentsMargins(left_margin, 0, 0, 0)
                # self.plot2.getPlotItem().setContentsMargins(left_margin, 0, 0, 0)
                # top_x_range = self.plot1.getViewBox().viewRange()[0]
                # self.plot2.setXRange(top_x_range[0], top_x_range[1])
                #self.plot2.getViewBox().setGeometry(self.plot1.getViewBox().sceneBoundingRect())
                lower, upper = min(self.spectrum.x), max(self.spectrum.x)
                self.plot2.setXRange(lower, upper)
                self.plot1.setXRange(lower, upper)
                self.align_button.setText('Reset X Axis')
        else: # Reset case
            self.plot1.autoRange()
            self.plot2.autoRange()
            self.align_button.setText('Align X Axis')

    def load_database_file(self):
        fname = QFileDialog.getOpenFileName(self, 'Open Database', filter="Database Files (*.db);;All Files (*)")
        if fname[0]:
            self.database_path = Path(fname[0])
            self.database_label.setText(f"Database: {self.database_path.name}")

    def load_unknown_spectrum(self):
        fname = QFileDialog.getOpenFileName(self, 'Select Raman Spectrum')
        if fname[0]:
            self.unknown_spectrum_path = Path(fname[0])
            command = LoadSpectrumCommand(self, *get_xy_from_file(self.unknown_spectrum_path))
            self.command_history.execute(command)

    def baseline_callback(self):
        if self.button_baseline.text() == "Estimate Baseline":
            lam = self.lineedit_lambda.text()
            lam = float(lam)
            command = EstimateBaselineCommand(self, baseline_als(self.spectrum.y, lam=lam))
            self.command_history.execute(command)
        else:
            command = CorrectBaselineCommand(self)
            self.command_history.execute(command)

    def search_database(self):
        if self.database_label.text() == "Database: None selected":
            # Show an error message
            QMessageBox.critical(self, 'Error', 'Please select a database first.')
            return
        mineral_name = self.mineral_input.text()
        wavelength = self.wavelength_input.text()

        connection = sqlite3.connect(self.database_path)
        cursor = connection.cursor()

        # Convert the mineral name to lowercase
        mineral_name_lower = mineral_name.lower()

        # Search takes place in its own thread (not quite working yet)
        # TODO fix threading
        if wavelength != '':
            # Use the LOWER function on names column and = operator for comparison
            cursor.execute("SELECT filename, data_x, data_y FROM Spectra WHERE LOWER(names) = ? AND wavelength=?", (mineral_name_lower, wavelength))
        else:
            cursor.execute("SELECT filename, data_x, data_y FROM Spectra WHERE LOWER(names) = ?", (mineral_name_lower,))
        results = cursor.fetchall()

        # Populate the results list
        self.results_list.clear()
        self.data_to_plot = {}
        for result in results:
            self.results_list.addItem(result[0])
            self.data_to_plot[result[0]] = (result[1], result[2])

        connection.close()  
        

    def plot_selected_spectra(self):
        selected_files = [item.text() for item in self.results_list.selectedItems()]
        
        # Clear previous plots
        self.plot2.clear()

        for file in selected_files:
            data_x, data_y = self.data_to_plot[file]
            x = deserialize(data_x)
            y = deserialize(data_y)
            y = y / max(y)
            self.plot2.plot(x, y)
        
        self.plot2.autoRange()

    def toggle_labels_callback(self):
        # Remove any previous text items (assuming you have them stored in a list attribute `self.peak_texts`)
        if hasattr(self, 'peak_texts') and self.peak_texts:
            for text_item in self.peak_texts:
                self.plot1.removeItem(text_item)
            self.peak_texts = []

        show = self.button_show_peak_labels.text() == 'Show Labels'

        if show:
            # Create and add the text items to the plot
            for x, y in zip(self.peaks_x, self.peaks_y):
                text_item = pg.TextItem(str(round(x, 1)), anchor=(0, 0), color=(255, 0, 0), angle=90)
                text_item.setPos(x, y)  # Adjusting the y position to be slightly above the peak
                self.plot1.addItem(text_item)
                if not hasattr(self, 'peak_texts'):
                    self.peak_texts = []
                self.peak_texts.append(text_item)
            self.button_show_peak_labels.setText('Hide Labels')
        else:
            self.button_show_peak_labels.setText('Show Labels')
        
    def find_peaks(self):
        width = self.textbox_width.text()
        rel_height = self.textbox_rel_height.text()
        height = self.textbox_height.text()
        prominence = self.textbox_prominence.text()

        width = float(width) if width else None
        rel_height = float(rel_height) if rel_height else None
        height = float(height) if height else None
        prominence = float(prominence) if prominence else None

        self.peaks_x, self.peaks_y = get_peaks(
            self.spectrum.x, 
            self.spectrum.y, 
            width=width, 
            rel_height=rel_height, 
            height=height, 
            prominence=prominence)
        
        # if hasattr(self, 'peak_plot') and self.peak_plot:
        #     self.plot1.removeItem(self.peak_plot)
        #     self.peak_plot = None
        # # TODO change this to add_scatter, handle internally by plot class
        # self.peak_plot = self.plot1.plot(self.peaks_x, self.peaks_y, pen=None, symbol='o', symbolSize=7, symbolBrush=(255, 0, 0))
        
        self.refresh_peaks_view()

    def refresh_peaks_view(self):

        self.plot1.set_scatter(self.peaks_x, self.peaks_y)

        if len(self.peaks_x) < 15:
            self.plot1_log.addItem(f'Peaks: {", ".join([str(x) for x in sorted(self.peaks_x)])}')
            self.textbox_peaks.setText(','.join([str(round(x,1)) for x in sorted(self.peaks_x)]))
        else:
            first_15_peaks = self.peaks_x[:15]
            self.plot1_log.addItem(f'Peaks: {", ".join([str(x) for x in sorted(first_15_peaks)])}...')
            self.textbox_peaks.setText(','.join([str(round(x,1)) for x in sorted(first_15_peaks)]))

    def on_search(self):
        if self.database_label.text() == "Database: None selected":
            # Show an error message
            QMessageBox.critical(self, 'Error', 'Please select a database first.')
            return
    
        # 1. Get values from textboxes
        peaks = self.textbox_peaks.text().split(',')
        peaks = [float(x) for x in peaks]
        tolerance = float(self.textbox_tolerance.text())
        
        # 2. Call search function
        result = find_spectrum_matches(self.database_path, peaks, tolerance) # Dict with keys 1,2,3
        unqiue_singletons = sorted(get_unique_mineral_combinations_optimized(self.database_path, result[1]))
        unique_pairs = sorted(get_unique_mineral_combinations_optimized(self.database_path, result[2]))
        unique_triples = sorted(get_unique_mineral_combinations_optimized(self.database_path, result[3]))
        msg_singletons = f'Found {len(unqiue_singletons)} unique mineral(s) containing your peak(s):\n'
        msg_pairs = f'Found {len(unique_pairs)} unique combinations of 2 minerals matching your peak(s):\n'
        msg_triples = f'Found {len(unique_triples)} unique combinations of 3 minerals matching your peak(s):\n'
        
        # 3. Populate the QTextEdits with the results:
        self.result_single.setText(msg_singletons)
        self.result_double.setText(msg_pairs)
        self.result_triple.setText(msg_triples)

        for line in unqiue_singletons:
            self.result_single.append(line[0])
        for line in unique_pairs:
            self.result_double.append(f'{line[0]},   {line[1]}')
        for line in unique_triples:
            self.result_triple.append(f'{line[0]},   {line[1]},   {line[2]}')

    def on_point_added(self, x: float, y: float):
        command = AddPeakPointCommand(self, x, y)
        self.command_history.execute(command)

    def on_point_removed(self, idx: int):
        command = RemovePeakPointCommand(self, idx)
        self.command_history.execute(command)

    def suggest_crop(self):
        idx = get_crop_index_suggestion(self.spectrum.y)
        self.plot1.set_crop_region(self.spectrum.x[0], self.spectrum.x[idx])

    def fit_peaks(self):
        #command = FitPeaksCommand(self, self.peaks_x)
        command = FitPeaksCommand2(self, self.peaks_x)
        self.command_history.execute(command)

    # Function to update Gaussian curves
    def update_gaussians(self):
        if self.updating_lines:
            return  # Avoid updating when changing lines programmatically
    
        # Find which peak to edit from the dropdown
        selected_idx = self.dropdown_edit_peak.currentIndex()
        key = f'Peak {selected_idx}'  # 1-indexed in keys, but there is a placeholder in dropdown
        
        # Get the new peak params from the control lines
        height_new = self.peak_line.value()
        center_new = self.center_line.value()
        sigma_new = abs(self.sigma_line.value() - center_new)
        
        # Update the dictionary
        self.fit_stats_2[key]['Height'] = height_new
        self.fit_stats_2[key]['Center'] = center_new
        self.fit_stats_2[key]['Sigma'] = sigma_new
    
        # Update the selected Gaussian curve
        new_x = np.linspace(min(self.spectrum.x), max(self.spectrum.x), 10_000)
        y_sum = np.zeros(new_x.shape)
        for i, param in enumerate(self.fit_stats_2.values()):
            y_new = gaussian(new_x, param['Height'], param['Center'], param['Sigma'])
            y_sum += y_new
            self.gaussians[i].setData(new_x, y_new)
    
        # Update the sum curve
        self.gaussian_sum.setData(new_x, y_sum)

    # Function to update control lines when a new peak is selected
    def update_control_lines(self):
        self.updating_lines = True  # Prevent update_gaussian from being triggered
    
        selected_idx = self.dropdown_edit_peak.currentIndex()
        if selected_idx >= 1:
            key = f'Peak {selected_idx}' 

            self.peak_line.setValue(self.fit_stats_2[key]['Height'])
            self.center_line.setValue(self.fit_stats_2[key]['Center'])
            self.sigma_line.setValue(self.fit_stats_2[key]['Center'] + self.fit_stats_2[key]['Sigma'])  # Offset by mu

            self.plot1.addItem(self.peak_line)
            self.plot1.addItem(self.center_line)
            self.plot1.addItem(self.sigma_line)
        
        else:
            self.plot1.removeItem(self.peak_line)
            self.plot1.removeItem(self.center_line)
            self.plot1.removeItem(self.sigma_line)
    
        self.updating_lines = False  # Re-enable updates

    # Function to move both center and width lines when the center line is moved
    def move_center(self):
        if self.updating_lines:
            return  # Avoid recursive updating
    
        self.updating_lines = True  # Block signals during update
        selected_idx = self.dropdown_edit_peak.currentIndex()
        key = f'Peak {selected_idx}'
    
        mu_new = self.center_line.value()  # Get new center value
        self.fit_stats_2[key]['Center'] = mu_new  # Update center
    
        # Move the width line relative to the new center (mu + sigma)
        self.sigma_line.setValue(mu_new + self.fit_stats_2[key]['Sigma'])
    
        self.updating_lines = False  # Re-enable updates
        self.update_gaussians()  # Update the Gaussian

    # Function to update only the width (sigma) when the width line is moved
    def move_sigma(self):
        if self.updating_lines:
            return  # Avoid recursive updating
    
        selected_idx = self.dropdown_edit_peak.currentIndex()
        key = f'Peak {selected_idx}'
    
        # Get the new sigma value as the distance from the center (mu)
        sigma_new = abs(self.sigma_line.value() - self.fit_stats_2[key]['Center'])
        self.fit_stats_2[key]['Sigma'] = sigma_new
    
        self.update_gaussians()  # Update the Gaussian



if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = MainApp()
    if ex.config.get('show_whats_new', False):
        ex.show_whats_new()
    ex.showFullScreen()
    sys.exit(app.exec())