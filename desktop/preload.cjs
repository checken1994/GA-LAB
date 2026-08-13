const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('scpDesktop', {
  isDesktop: true,
  modelVersion: '1.6',
  appName: 'SCP DNA Desktop Control Center',
  notifyCritical: (payload) => ipcRenderer.invoke('notify-critical', payload),
});
