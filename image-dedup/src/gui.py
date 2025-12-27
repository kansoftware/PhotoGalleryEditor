"""
Модуль для ручного разбора кластеров изображений с использованием PyQt6.

Этот модуль предоставляет графический интерфейс (GUI) для просмотра групп
похожих изображений, найденных на этапе кластеризации. Пользователь может
просмотреть каждое изображение в кластере, пометить дубликаты для удаления
или проигнорировать кластер.

Основные компоненты:
- `ImageLoader`: QThread для асинхронной загрузки и масштабирования изображений.
- `MainWindow`: Основное окно приложения, отображающее список кластеров и сетку
  с изображениями выбранного кластера.
- `run_gui`: Функция для запуска приложения.
"""
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.db import ImageRecord, SessionLocal


class ImageLoader(QThread):
    """
    Поток для асинхронной загрузки изображений.

    Загружает изображения из списка, масштабирует их до размера миниатюр
    и отправляет сигнал `loaded` с готовым QPixmap.
    """

    loaded = pyqtSignal(int, str, QPixmap)  # idx_in_layout, path, pixmap

    def __init__(self, items: List[Tuple[int, str]]):
        """
        Инициализирует загрузчик изображений.

        Args:
            items: Список кортежей, где каждый кортеж содержит
                   индекс виджета в сетке и путь к файлу.
        """
        super().__init__()
        self.items = items

    def run(self) -> None:
        """Запускает процесс загрузки изображений."""
        for idx, path_str in self.items:
            p = Path(path_str)
            if p.exists():
                pix = QPixmap(path_str)
                if not pix.isNull():
                    # Масштабируем для миниатюры
                    pix = pix.scaled(
                        300,
                        300,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self.loaded.emit(idx, path_str, pix)


class MainWindow(QMainWindow):
    """
    Основное окно приложения для просмотра дубликатов.

    Отображает список кластеров слева и сетку с изображениями
    выбранного кластера справа. Позволяет выполнять действия над
    кластерами, такие как "оставить один" или "игнорировать".
    """

    def __init__(self, readonly: bool = False):
        """
        Инициализирует главное окно.

        Args:
            readonly: Если True, все кнопки для изменения данных
                      будут отключены.
        """
        super().__init__()
        self.setWindowTitle("Разбор дубликатов изображений")
        self.resize(1200, 800)

        self.readonly = readonly
        if self.readonly:
            print("readonly mode")

        self.session: Session = SessionLocal()

        self.current_cluster_id: Optional[int] = None
        self.cluster_images: List[ImageRecord] = []

        self.init_ui()
        self.init_menu()
        self.load_clusters()

    def init_ui(self) -> None:
        """Инициализирует пользовательский интерфейс."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Этот вызов был удален, но он нужен. Восстановим его в правильном виде.
        self.setMenuBar(QMenuBar(self))

        # Панель слева: Список кластеров
        left_layout = QVBoxLayout()
        self.cluster_list = QListWidget()
        self.cluster_list.itemClicked.connect(self.on_cluster_selected)
        left_layout.addWidget(QLabel("Кластеры (группы > 1)"))
        left_layout.addWidget(self.cluster_list)

        # Панель справа: Сетка изображений + Действия
        right_layout = QVBoxLayout()

        # Панель инструментов
        action_layout = QHBoxLayout()
        self.btn_keep_first = QPushButton("Оставить первый, удалить остальные")
        self.btn_keep_first.clicked.connect(self.action_keep_first)
        self.btn_ignore = QPushButton("Игнорировать (отметить как просмотрено)")
        self.btn_ignore.clicked.connect(self.action_ignore)
        self.btn_delete_all = QPushButton("Удалить все")
        self.btn_delete_all.clicked.connect(self.action_delete_all)

        action_layout.addWidget(self.btn_keep_first)
        action_layout.addWidget(self.btn_ignore)
        action_layout.addWidget(self.btn_delete_all)

        # Деактивируем кнопки до выбора кластера
        self.btn_keep_first.setEnabled(False)
        self.btn_ignore.setEnabled(False)
        self.btn_delete_all.setEnabled(False)
        right_layout.addLayout(action_layout)

        # Область прокрутки для изображений
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.scroll_area.setWidget(self.grid_widget)
        right_layout.addWidget(self.scroll_area)

        main_layout.addLayout(left_layout, 1)
        main_layout.addLayout(right_layout, 3)

    def init_menu(self) -> None:
        """Инициализирует меню приложения."""
        commands_menu = self.menuBar().addMenu("Команды")

        # 1. Отменить все изменения
        action_revert = QAction("Отменить все изменения", self)
        action_revert.triggered.connect(self.action_revert_all_changes)
        commands_menu.addAction(action_revert)

        # 2. Удалить все помеченные файлы
        action_delete = QAction("Удалить все помеченные файлы", self)
        action_delete.triggered.connect(self.action_delete_marked_files)
        if self.readonly:
            action_delete.setEnabled(False)
        commands_menu.addAction(action_delete)

        commands_menu.addSeparator()

        # 3. Закрыть
        action_close = QAction("Закрыть", self)
        action_close.triggered.connect(self.close)
        commands_menu.addAction(action_close)

    def load_clusters(self) -> None:
        """Загружает из БД список кластеров, требующих разбора."""
        stmt = (
            select(ImageRecord.cluster_id)
            .where(ImageRecord.cluster_id.is_not(None), ImageRecord.reviewed.is_(False))
            .distinct()
        )
        clusters = self.session.execute(stmt).scalars().all()

        self.cluster_list.clear()
        for cid in clusters:
            self.cluster_list.addItem(f"Кластер #{cid}")

    def on_cluster_selected(self, item: QListWidgetItem) -> None:
        """Обрабатывает выбор кластера из списка."""
        txt = item.text()
        cid = int(txt.split("#")[1])
        self.current_cluster_id = cid
        self.load_cluster_images(cid)

        # Активируем кнопки после выбора кластера
        if not self.readonly:
            self.btn_keep_first.setEnabled(True)
            self.btn_ignore.setEnabled(True)
            self.btn_delete_all.setEnabled(True)

    def load_cluster_images(self, cluster_id: int) -> None:
        """Загружает и отображает изображения для выбранного кластера."""
        # Очищаем сетку
        for i in reversed(range(self.grid_layout.count())):
            item = self.grid_layout.itemAt(i)
            if item:
                widget = item.widget()
                if widget:
                    widget.setParent(None)

        stmt = (
            select(ImageRecord).where(ImageRecord.cluster_id == cluster_id).order_by(ImageRecord.id)
        )
        self.cluster_images = list(self.session.execute(stmt).scalars().all())

        load_queue: List[Tuple[int, str]] = []

        for i, img_rec in enumerate(self.cluster_images):
            # Контейнер для одного изображения
            container = QWidget()
            vbox = QVBoxLayout(container)

            lbl_img = QLabel("Загрузка...")
            lbl_img.setFixedSize(300, 300)
            lbl_img.setStyleSheet("border: 1px solid gray;")
            lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)

            size_kb = (img_rec.size_bytes or 0) / 1024
            lbl_info = QLabel(f"{Path(str(img_rec.path)).name}\n{size_kb:.1f} КБ")

            btn_del = QPushButton("Пометить к удалению")
            btn_del.setCheckable(True)
            if self.readonly:
                btn_del.setEnabled(False)

            vbox.addWidget(lbl_img)
            vbox.addWidget(lbl_info)
            vbox.addWidget(btn_del)

            self.grid_layout.addWidget(container, i // 3, i % 3)

            # Сохраняем ссылки для последующей логики
            container.setProperty("rec_id", img_rec.id)
            container.setProperty("img_label", lbl_img)
            container.setProperty("del_btn", btn_del)

            load_queue.append((i, img_rec.path))

        # Асинхронная загрузка
        self.loader = ImageLoader(load_queue)
        self.loader.loaded.connect(self.on_image_loaded)
        self.loader.start()

    def on_image_loaded(self, idx: int, path: str, pixmap: QPixmap) -> None:
        """Слот, вызываемый после загрузки изображения."""
        # Находим виджет в сетке по его позиции
        item = self.grid_layout.itemAtPosition(idx // 3, idx % 3)
        if item:
            widget = item.widget()
            if widget:
                lbl = widget.property("img_label")
                if isinstance(lbl, QLabel):
                    lbl.setPixmap(pixmap)
                    lbl.setText("")

    def action_keep_first(self) -> None:
        """
        Обрабатывает действие "Оставить первый, удалить остальные".

        Первое изображение в кластере остается, остальные помечаются
        к удалению (`to_delete=True`). Весь кластер помечается как
        просмотренный (`reviewed=True`).
        """
        if self.current_cluster_id is None:
            return

        # Первый оставляем, остальные помечаем к удалению
        first = True
        for img in self.cluster_images:
            img.reviewed = True
            if not first:
                img.to_delete = True
                print(f"Помечено к удалению: {img.path}")
            first = False

        self.session.commit()
        self.remove_current_cluster_from_list()

    def action_ignore(self) -> None:
        """
        Обрабатывает действие "Игнорировать".

        Все изображения в кластере помечаются как просмотренные
        (`reviewed=True`), но не помечаются к удалению.
        """
        if self.current_cluster_id is None:
            return
        for img in self.cluster_images:
            img.reviewed = True
        self.session.commit()
        self.remove_current_cluster_from_list()

    def action_delete_all(self) -> None:
        """
        Обрабатывает действие "Удалить все".

        Все изображения в кластере помечаются к удалению (`to_delete=True`).
        Кластер помечается как просмотренный (`reviewed=True`).
        """
        if self.current_cluster_id is None:
            return

        # Запрашиваем подтверждение у пользователя
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Вы уверены, что хотите пометить ВСЕ изображения в этом кластере к удалению?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.No:
            return

        for img in self.cluster_images:
            img.reviewed = True
            img.to_delete = True
            print(f"Помечено к удалению: {img.path}")

        self.session.commit()
        self.remove_current_cluster_from_list()

    def remove_current_cluster_from_list(self) -> None:
        """
        Удаляет текущий кластер из списка и очищает сетку.
        """
        row = self.cluster_list.currentRow()
        if row != -1:
            self.cluster_list.takeItem(row)

        # Очищаем сетку
        for i in reversed(range(self.grid_layout.count())):
            item = self.grid_layout.itemAt(i)
            if item:
                widget = item.widget()
                if widget:
                    widget.setParent(None)
        self.current_cluster_id = None

        # Деактивируем кнопки после обработки
        self.btn_keep_first.setEnabled(False)
        self.btn_ignore.setEnabled(False)
        self.btn_delete_all.setEnabled(False)

    def action_revert_all_changes(self) -> None:
        """Отменяет все пометки `to_delete` во всей базе."""
        if self.readonly:
            QMessageBox.warning(self, "Режим чтения", "Нельзя вносить изменения.")
            return

        stmt = update(ImageRecord).values(to_delete=False, reviewed=False)
        self.session.execute(stmt)
        self.session.commit()

        # Обновляем вид кнопок в текущем кластере, если он выбран
        if self.current_cluster_id is not None:
            self.load_cluster_images(self.current_cluster_id)

        QMessageBox.information(
            self, "Готово", "Все пометки 'к удалению' и 'просмотрено' были сняты."
        )
        self.load_clusters()  # Обновляем список кластеров

    def action_delete_marked_files(self) -> None:
        """Переименовывает все файлы, помеченные к удалению."""
        if self.readonly:
            QMessageBox.warning(self, "Режим чтения", "Нельзя удалять файлы.")
            return

        stmt = select(ImageRecord).where(ImageRecord.to_delete.is_(True))
        records_to_delete = list(self.session.execute(stmt).scalars().all())

        if not records_to_delete:
            QMessageBox.information(self, "Нечего удалять", "Нет файлов, помеченных к удалению.")
            return

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            (
                f"Вы уверены, что хотите переименовать {len(records_to_delete)} файлов,"
                " добавив суффикс '_deleted'?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            deleted_count = 0
            errors = []
            for rec in records_to_delete:
                try:
                    p = Path(rec.path)
                    new_path = p.with_suffix(p.suffix + "._deleted")
                    if p.exists():
                        p.rename(new_path)
                        rec.path = str(new_path)
                        deleted_count += 1
                except Exception as e:
                    errors.append(f"Не удалось переименовать {rec.path}: {e}")

            self.session.commit()

            msg = f"Переименовано {deleted_count} файлов."
            if errors:
                msg += "\n\nОшибки:\n" + "\n".join(errors)

            QMessageBox.information(self, "Отчет", msg)
            self.load_clusters()  # Обновляем список кластеров


def run_gui(readonly: bool) -> None:
    """
    Запускает GUI-приложение для разбора дубликатов.

    Args:
        readonly: Если True, приложение запустится в режиме "только для чтения".
    """
    app = QApplication(sys.argv)
    window = MainWindow(readonly=readonly)
    window.show()
    sys.exit(app.exec())
