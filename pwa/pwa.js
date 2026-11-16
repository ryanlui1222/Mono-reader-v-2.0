(() => {
  if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
  const standalone = matchMedia('(display-mode: standalone)');
  const area = document.createElement('div');
  area.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:12px 0';
  const button = document.createElement('button');
  button.type = 'button'; button.textContent = '＋ 安裝 App';
  button.hidden = standalone.matches || navigator.standalone === true;
  const help = document.createElement('p');
  help.setAttribute('role','status');
  help.style.cssText = 'font:13px/1.7 system-ui;width:100%;margin:0';
  area.append(button,help);
  (document.querySelector('main') || document.body).prepend(area);
  let promptEvent;
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault(); promptEvent = event;
    button.hidden = standalone.matches;
  });
  window.addEventListener('appinstalled', () => {
    promptEvent = null; button.hidden = true; help.textContent = '已安裝，可從主畫面開啟 Monoreader。';
  });
  standalone.addEventListener('change', () => { button.hidden = standalone.matches; });
  button.addEventListener('click', async () => {
    if (!promptEvent) {
      help.textContent = 'Android：請用 Chrome 開啟，點右上角 ⋮ →「新增至主畫面」或「安裝應用程式」。電腦：使用 Chrome／Edge 網址列的安裝圖示。若尚未出現，重新整理後再試；已安裝時可直接從圖示開啟。';
      return;
    }
    const pending = promptEvent; promptEvent = null;
    try {
      await pending.prompt();
      const choice = await pending.userChoice;
      help.textContent = choice.outcome === 'accepted' ? '正在安裝，完成後可從主畫面開啟。' : '已取消安裝，你仍可繼續使用網頁。';
    } catch (_) { help.textContent = '請改用瀏覽器選單的「安裝應用程式」。'; }
  });
  navigator.serviceWorker.register('/sw.js', {scope:'/', updateViaCache:'none'}).then(reg => {
    let updateButton;
    function offerUpdate() {
      if (!reg.waiting || !navigator.serviceWorker.controller || updateButton) return;
      updateButton = document.createElement('button'); updateButton.type = 'button';
      updateButton.textContent = '更新 App'; area.append(updateButton);
      updateButton.addEventListener('click', () => {
        navigator.serviceWorker.addEventListener('controllerchange', () => location.reload(), {once:true});
        reg.waiting?.postMessage({type:'ACTIVATE_UPDATE'});
      });
    }
    offerUpdate();
    reg.addEventListener('updatefound', () => {
      const worker = reg.installing;
      worker?.addEventListener('statechange', () => { if (worker.state === 'installed') offerUpdate(); });
    });
  }).catch(() => { help.textContent = 'App 安裝元件未能載入，請連線後重新整理。網頁仍可使用。'; });
})();
