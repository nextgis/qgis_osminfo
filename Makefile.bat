cd ui
pyuic4 -o ui_aboutdialogbase.py aboutdialogbase.ui
cd ..
pyrcc4 -o resources.py resources.qrc
lrelease i18n\osminfo_ru.ts
cd ..
zip -r osminfo.zip osminfo -x \*.pyc \*.json \*.ts \*.ui \*.qrc \*.pro \*~ \*.git\* \*.svn\* \*Makefile*