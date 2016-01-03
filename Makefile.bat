cd ui
pyuic4 -o ui_aboutdialogbase.py aboutdialogbase.ui
pyuic4 -o ui_settingsdialogbase.py settingsdialogbase.ui
cd ..
pyrcc4 -o resources.py resources.qrc
pylupdate4 -verbose osminfo.pro
lrelease i18n\osminfo_ru.ts
cd ..
zip -r osminfo.zip osminfo -x \*.pyc \*.json \*.ts \*.ui \*.qrc \*.pro \*~ \*.git\* \*.svn\* \*Makefile*
