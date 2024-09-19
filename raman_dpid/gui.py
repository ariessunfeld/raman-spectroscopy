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
    QScrollArea
)
from PyQt6 import QtCore 
from PyQt6.QtGui import QColor, QShortcut, QKeySequence
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtCore import (
    Qt,
    qInstallMessageHandler
)
import pyqtgraph as pg

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
        
        self.peak_line = None
        self.center_line = None
        self.sigma_line = None

        self.updating_lines = False

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
        #self.plot1 = pg.PlotWidget(self)
        self.plot1 = CroppablePlotWidget(self)
        #self.plot1.setLabel('left', 'Intensity')
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
        self.button_print_fits = QPushButton('Print Fits', self)
        self.button_print_fits.clicked.connect(self.print_fit_stats)
        plot1_buttons_layout.addWidget(self.button_print_fits)

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

        # LisWidget: Log for Plot 1
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
        #self.main_widget = QWidget(self)
        #self.setCentralWidget(self.main_widget)
        #self.main_widget.setLayout(main_layout)
        #self.show()


    def print_fit_stats(self):
        if self.fit_stats_2 is not None:
            for peak, stats in self.fit_stats_2.items():
                print(peak)
                for key, val in stats.items():
                    if key in ['Center', 'Sigma', 'Height']:
                        print(f'\t{key}: {val}')


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
        fname, _ = QFileDialog.getSaveFileName(self, "Save Spectrum", str(suggested_path), "Text Files (*.txt);;All Files (*)")

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
        fname = QFileDialog.getOpenFileName(self, 'Open Database', '..', "Database Files (*.db);;All Files (*)")
        if fname[0]:
            self.database_path = Path(fname[0])
            self.database_label.setText(f"Database: {self.database_path.name}")

    def load_unknown_spectrum(self):
        fname = QFileDialog.getOpenFileName(self, 'Select Raman Spectrum', '..')
        if fname[0]:
            self.unknown_spectrum_path = Path(fname[0])
            command = LoadSpectrumCommand(self, *get_xy_from_file(self.unknown_spectrum_path))
            self.command_history.execute(command)

    def baseline_callback(self):
        if self.button_baseline.text() == "Estimate Baseline":
            command = EstimateBaselineCommand(self, baseline_als(self.spectrum.y))
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