from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = collect_submodules('scipy') + ['numpy.fft']
datas = collect_data_files('scipy')