import sys
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QListWidget, QLabel, QPushButton, QScrollArea, QGridLayout, QMessageBox)
from PyQt6.QtGui import QPixmap, QAction
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from sqlalchemy import select, update

from src.db import SessionLocal, ImageRecord

class ImageLoader(QThread):
    loaded = pyqtSignal(int, str, QPixmap) # idx_in_layout, path, pixmap

    def __init__(self, items):
        super().__init__()
        self.items = items # list of (idx, path)

    def run(self):
        for idx, path_str in self.items:
            p = Path(path_str)
            if p.exists():
                pix = QPixmap(path_str)
                if not pix.isNull():
                    # Scale for thumbnail
                    pix = pix.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    self.loaded.emit(idx, path_str, pix)

class MainWindow(QMainWindow):
    def __init__(self, readonly=False):
        super().__init__()
        self.setWindowTitle("Image Deduplication Review")
        self.resize(1200, 800)
        self.readonly = readonly
        self.session = SessionLocal()
        
        self.current_cluster_id = None
        self.cluster_images = [] # list of ImageRecord objects
        
        self.init_ui()
        self.load_clusters()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Left Panel: Cluster List
        left_layout = QVBoxLayout()
        self.cluster_list = QListWidget()
        self.cluster_list.itemClicked.connect(self.on_cluster_selected)
        left_layout.addWidget(QLabel("Clusters (Groups > 1)"))
        left_layout.addWidget(self.cluster_list)
        
        # Right Panel: Image Grid + Actions
        right_layout = QVBoxLayout()
        
        # Actions Toolbar
        action_layout = QHBoxLayout()
        self.btn_keep_first = QPushButton("Keep First, Delete Others")
        self.btn_keep_first.clicked.connect(self.action_keep_first)
        self.btn_ignore = QPushButton("Ignore (Mark Reviewed)")
        self.btn_ignore.clicked.connect(self.action_ignore)
        
        if self.readonly:
            self.btn_keep_first.setEnabled(False)
            
        action_layout.addWidget(self.btn_keep_first)
        action_layout.addWidget(self.btn_ignore)
        right_layout.addLayout(action_layout)
        
        # Scroll Area for Images
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.scroll.setWidget(self.grid_widget)
        right_layout.addWidget(self.scroll)

        main_layout.addLayout(left_layout, 1)
        main_layout.addLayout(right_layout, 3)

    def load_clusters(self):
        # Загружаем ID кластеров, где есть нерассмотренные изображения
        stmt = select(ImageRecord.cluster_id).where(
            ImageRecord.cluster_id.is_not(None),
            ImageRecord.reviewed == False
        ).distinct()
        clusters = self.session.execute(stmt).scalars().all()
        
        self.cluster_list.clear()
        for cid in clusters:
            self.cluster_list.addItem(f"Cluster #{cid}")

    def on_cluster_selected(self, item):
        txt = item.text()
        cid = int(txt.split("#")[1])
        self.current_cluster_id = cid
        self.load_cluster_images(cid)

    def load_cluster_images(self, cluster_id):
        # Clear grid
        for i in reversed(range(self.grid_layout.count())): 
            self.grid_layout.itemAt(i).widget().setParent(None)
            
        stmt = select(ImageRecord).where(ImageRecord.cluster_id == cluster_id).order_by(ImageRecord.id)
        self.cluster_images = self.session.execute(stmt).scalars().all()
        
        load_queue = []
        
        for i, img_rec in enumerate(self.cluster_images):
            # Container
            container = QWidget()
            vbox = QVBoxLayout(container)
            
            lbl_img = QLabel("Loading...")
            lbl_img.setFixedSize(300, 300)
            lbl_img.setStyleSheet("border: 1px solid gray;")
            lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            lbl_info = QLabel(f"{Path(img_rec.path).name}\n{img_rec.size_bytes/1024:.1f} KB")
            
            btn_del = QPushButton("Mark Delete")
            btn_del.setCheckable(True)
            if self.readonly: btn_del.setEnabled(False)
            
            vbox.addWidget(lbl_img)
            vbox.addWidget(lbl_info)
            vbox.addWidget(btn_del)
            
            self.grid_layout.addWidget(container, i // 3, i % 3)
            
            # Store references for logic
            container.setProperty("rec_id", img_rec.id)
            container.setProperty("img_label", lbl_img)
            container.setProperty("del_btn", btn_del)
            
            load_queue.append((i, img_rec.path))

        # Async load
        self.loader = ImageLoader(load_queue)
        self.loader.loaded.connect(self.on_image_loaded)
        self.loader.start()

    def on_image_loaded(self, idx, path, pixmap):
        # Find widget at grid position
        item = self.grid_layout.itemAtPosition(idx // 3, idx % 3)
        if item:
            widget = item.widget()
            lbl = widget.property("img_label")
            lbl.setPixmap(pixmap)
            lbl.setText("")

    def action_keep_first(self):
        if not self.current_cluster_id: return
        
        # Первый оставляем, остальные to_delete
        first = True
        for img in self.cluster_images:
            img.reviewed = True
            if not first:
                img.to_delete = True
                print(f"Marked for deletion: {img.path}")
            first = False
        
        self.session.commit()
        self.remove_current_cluster_from_list()

    def action_ignore(self):
        if not self.current_cluster_id: return
        for img in self.cluster_images:
            img.reviewed = True
        self.session.commit()
        self.remove_current_cluster_from_list()

    def remove_current_cluster_from_list(self):
        row = self.cluster_list.currentRow()
        self.cluster_list.takeItem(row)
        # Clear grid
        for i in reversed(range(self.grid_layout.count())): 
            self.grid_layout.itemAt(i).widget().setParent(None)
        self.current_cluster_id = None

def run_gui(readonly: bool):
    app = QApplication(sys.argv)
    window = MainWindow(readonly=readonly)
    window.show()
    sys.exit(app.exec())