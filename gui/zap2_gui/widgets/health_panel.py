"""Compact separate health layers; explicit snapshot refresh without probes."""
from ..qt_compat import require_pyqt
from ..adapters.discovery_health import load_health

def make_health_panel(root):
    _QtCore,QtWidgets=require_pyqt()
    group=QtWidgets.QGroupBox('Состояние: runtime / сеть / приложение (снимок)')
    group.setCheckable(True); group.setChecked(False)
    layout=QtWidgets.QVBoxLayout(group)
    refresh=QtWidgets.QPushButton('Обновить состояние')
    technical=QtWidgets.QCheckBox('Технические ID и данные проверок')
    table=QtWidgets.QTableWidget(0,4)
    table.setObjectName('globalHealthTable')
    table.setHorizontalHeaderLabels(['Слой','Проверка','Результат','Следующий шаг'])
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setMaximumHeight(220); table.horizontalHeader().setStretchLastSection(True)
    hint=QtWidgets.QLabel('Нет снимка. Раскройте панель и обновите. PASS относится к указанной проверке и запуску.')
    hint.setWordWrap(True)
    layout.addWidget(hint); layout.addWidget(refresh); layout.addWidget(technical); layout.addWidget(table)
    snapshot={"rows":()}
    def render():
        rows=snapshot["rows"]; table.setRowCount(len(rows))
        layer_labels={"runtime":"Запуск","local":"Локальное","network":"Сеть","app":"Приложение"}
        status_labels={"PASS":"Пройдено","FAIL":"Сбой","UNKNOWN":"Нет данных","STOPPED":"Остановлен"}
        labels={"discord.bootstrap.gateway":"Discord Gateway","vesktop.navigation":"Окно Vesktop","vesktop.bootstrap":"Запуск Vesktop"}
        next_steps={"runtime":"Проверьте состояние и принадлежность ресурсов","local":"Проверьте локальное подключение туннеля","network":"Проверьте HTTPS через выбранный туннель","app":"Проверьте обязательные соединения приложения"}
        for i,r in enumerate(rows):
            title=labels.get(r.label,r.label.replace('route.https:','HTTPS: '))
            values=(r.layer,r.label,r.status,r.evidence+' → '+r.next_action) if technical.isChecked() else (layer_labels[r.layer],title,status_labels[r.status],next_steps[r.layer])
            for j,text in enumerate(values):
                item=QtWidgets.QTableWidgetItem(text); item.setToolTip(r.evidence+' → '+r.next_action); table.setItem(i,j,item)
        table.resizeColumnsToContents()
        table.setColumnWidth(3,260)
        table.resizeRowsToContents()
        table.setFixedHeight(min(180, table.horizontalHeader().height()+sum(table.rowHeight(i) for i in range(table.rowCount()))+4))
    def refresh_data():
        snapshot["rows"]=load_health(root); render()
        from datetime import datetime
        hint.setText('Снимок '+datetime.now().strftime('%H:%M:%S')+'. Изменения после снимка требуют обновления. Локальный SOCKS PASS не доказывает TLS/Discord.')
    def toggle(checked):
        for w in (hint,refresh,technical,table): w.setVisible(checked)
    group.toggled.connect(toggle); refresh.clicked.connect(refresh_data); technical.toggled.connect(render); toggle(False)
    group.refresh_health=refresh_data
    return group
