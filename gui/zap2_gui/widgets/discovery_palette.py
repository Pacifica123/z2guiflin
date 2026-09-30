"""Global discovery; page-local preset search remains owned by its page."""
from pathlib import Path
import sys
from ..qt_compat import require_pyqt
from ..models.discovery import search, direct_invoke_allowed
from ..models.error_envelope import error_envelope


def make_discovery_palette(parent, root: Path, focus_page):
    QtCore, QtWidgets = require_pyqt()
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle('Найти действие, настройку или понятие — Ctrl+K')
    dialog.resize(780,640)
    layout = QtWidgets.QVBoxLayout(dialog)
    query = QtWidgets.QLineEdit(); query.setObjectName('globalDiscoveryQuery')
    query.setPlaceholderText('Например: безопасно запустить, VLESS, откат firewall, NFQUEUE, тема')
    matches = QtWidgets.QListWidget(); matches.setObjectName('globalDiscoveryResults')
    details = QtWidgets.QPlainTextEdit(); details.setReadOnly(True); details.setObjectName('discoveryDetails')
    technical = QtWidgets.QCheckBox('Показать технические ID и CLI')
    row = QtWidgets.QHBoxLayout()
    open_button = QtWidgets.QPushButton('Открыть раздел / подготовить действие')
    invoke_button = QtWidgets.QPushButton('Выполнить просмотр / проверку')
    row.addWidget(open_button); row.addWidget(invoke_button)
    layout.addWidget(query); layout.addWidget(matches); layout.addWidget(technical); layout.addWidget(details); layout.addLayout(row)
    state = {'entry':None}
    process = QtCore.QProcess(dialog)
    process.setWorkingDirectory(str(root))
    env = QtCore.QProcessEnvironment.systemEnvironment()
    env.insert('PYTHONPATH',str(root/'gui'))
    env.insert('PYTHONDONTWRITEBYTECODE','1')
    process.setProcessEnvironment(env)
    process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
    timer = QtCore.QTimer(dialog); timer.setSingleShot(True)
    timer.timeout.connect(process.kill)

    def show_help():
        e = state['entry']
        if e is None: return
        text = e.help_text
        if not technical.isChecked():
            text = '\n'.join(line for line in text.splitlines() if not line.startswith(('Технический ID:', 'CLI:')))
        details.setPlainText(text)
        invoke_button.setEnabled(e.kind == 'action' and direct_invoke_allowed(e.semantic_id) and process.state() == QtCore.QProcess.ProcessState.NotRunning)
        open_button.setEnabled(True)

    def select():
        item = matches.currentItem(); state['entry'] = item.data(QtCore.Qt.ItemDataRole.UserRole) if item else None
        if item: show_help()
        else:
            details.setPlainText('Совпадений нет. Попробуйте более короткий термин.'); invoke_button.setEnabled(False); open_button.setEnabled(False)

    def update():
        matches.clear()
        for e in search(query.text()):
            item = QtWidgets.QListWidgetItem(f'{e.label} · {e.kind}')
            item.setData(QtCore.Qt.ItemDataRole.UserRole,e); matches.addItem(item)
        if matches.count(): matches.setCurrentRow(0)
        else: select()

    def open_entry():
        e=state['entry']
        if e is None: return
        if e.kind == 'setting':
            dialog.hide(); focus_page(e.page,e.focus_target)
        else:
            # Focus the exact action/concept help here; related page is a route,
            # not a claim that all CLI-only operations have a GUI execution button.
            focus_page(e.page,None); details.setFocus()

    def invoke():
        e=state['entry']
        if e is None or e.kind != 'action' or not direct_invoke_allowed(e.semantic_id): return
        if process.state() != QtCore.QProcess.ProcessState.NotRunning: return
        invoke_button.setEnabled(False)
        details.setPlainText('Выполняется просмотр / проверка…')
        process.start(sys.executable,['-m','zap2_gui.app','--action',e.semantic_id])
        timer.start(30000)

    def finished(code,_status):
        timer.stop()
        output=bytes(process.readAllStandardOutput()).decode('utf-8','replace')
        if code:
            envelope=error_envelope('ACTION-FAILED','Действие вернуло ошибку; смотрите вывод ниже.',(f'exit={code}',))
            output=envelope.text()+'\n\n'+output
        details.setPlainText(output); select_enabled=state['entry']
        invoke_button.setEnabled(bool(select_enabled and select_enabled.kind == 'action' and direct_invoke_allowed(select_enabled.semantic_id)))
    process.finished.connect(finished)
    def process_error(_error):
        timer.stop()
        details.setPlainText(error_envelope('ACTION-START-FAILED','Не удалось запустить действие.',(process.errorString(),)).text())
        e=state['entry']
        invoke_button.setEnabled(bool(e and e.kind == 'action' and direct_invoke_allowed(e.semantic_id) and process.state() == QtCore.QProcess.ProcessState.NotRunning))
    process.errorOccurred.connect(process_error)
    dialog.finished.connect(lambda _result: process.kill() if process.state() != QtCore.QProcess.ProcessState.NotRunning else None)
    query.textChanged.connect(update); matches.currentRowChanged.connect(lambda _row: select())
    technical.toggled.connect(show_help); open_button.clicked.connect(open_entry); invoke_button.clicked.connect(invoke)
    invoke_button.setEnabled(False); open_button.setEnabled(False)
    dialog.query = query; dialog.details = details
    return dialog
