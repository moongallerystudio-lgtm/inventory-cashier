// Cleaned main.js: scanning (BarcodeDetector + Quagga fallback), cart, member, receipt
let currentScanTarget = null;
let videoStream = null;
let barcodeDetector = null;
let quaggaRunning = false;
let currentMember = null;
let lastImageDataUrl = null;
let lastRotation = 0;

async function startScan(targetId) {
  currentScanTarget = targetId;
  const videoWrapper = document.getElementById('videoWrapper');
  const scanVideo = document.getElementById('scanVideo');

  console.log('startScan target:', targetId);
  const isLocalhost = ['localhost', '127.0.0.1', '::1'].includes(location.hostname);
  if (!window.isSecureContext && !isLocalhost) {
    alert('当前访问不是安全上下文，浏览器无法直接打开摄像头。请通过 HTTPS 地址访问或手动输入条码。');
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert('当前浏览器不支持摄像头访问，无法进行实时扫码。请手动输入条码。');
    return;
  }

  // Prefer native BarcodeDetector when available
  if ('BarcodeDetector' in window) {
    try {
      barcodeDetector = new BarcodeDetector({ formats: ['ean_13', 'ean_8', 'code_128', 'qr_code', 'upc_e'] });
    } catch (error) {
      barcodeDetector = null;
    }
  }

  if (barcodeDetector) {
    try {
      videoStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      scanVideo.srcObject = videoStream;
      scanVideo.muted = true;
      videoWrapper.style.display = 'block';
      await scanVideo.play();
      scanFrame();
      return;
    } catch (error) {
      console.warn('摄像头打开或视频播放失败', error);
      alert('无法打开摄像头或自动播放视频失败：' + error.message + '。请手动输入条码或检查浏览器权限。');
      return;
    }
  }

  // Fallback: use QuaggaJS (loaded from CDN in templates)
  if (window.Quagga) {
    startQuagga(videoWrapper);
  } else {
    // Try to dynamically load Quagga, then start
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/@ericblade/quagga2/dist/quagga.min.js';
    script.onload = () => startQuagga(videoWrapper);
    script.onerror = () => alert('无法加载扫码回退库，请手动输入条形码。');
    document.head.appendChild(script);
  }
}

function startQuagga(videoWrapper) {
  if (!window.Quagga) {
    alert('扫码回退库未加载，请手动输入条形码。');
    return;
  }
  if (quaggaRunning) return;
  quaggaRunning = true;
  videoWrapper.style.display = 'block';
  Quagga.init({
    inputStream: {
      name: 'Live',
      type: 'LiveStream',
      target: videoWrapper,
      constraints: { facingMode: 'environment' },
    },
    decoder: {
      readers: ['ean_reader','ean_8_reader','code_128_reader','code_39_reader','upc_reader']
    },
    locate: true,
  }, function(err) {
    if (err) {
      console.error(err);
      alert('初始化扫码失败，请手动输入条形码。');
      quaggaRunning = false;
      videoWrapper.style.display = 'none';
      return;
    }
    Quagga.start();
  });
  Quagga.onDetected(function(result) {
    if (!result || !result.codeResult) return;
    const code = result.codeResult.code;
    stopQuagga();
    fillBarcode(code);
  });
}

function stopQuagga() {
  if (!quaggaRunning) return;
  try {
    Quagga.stop();
  } catch (e) {
    console.warn('Quagga stop error', e);
  }
  quaggaRunning = false;
  const videoWrapper = document.getElementById('videoWrapper');
  if (videoWrapper) videoWrapper.style.display = 'none';
}

async function scanFrame() {
  if (!videoStream) return;
  const scanVideo = document.getElementById('scanVideo');

  if (barcodeDetector) {
    try {
      const barcodes = await barcodeDetector.detect(scanVideo);
      if (barcodes && barcodes.length > 0) {
        const code = barcodes[0].rawValue;
        stopScan();
        fillBarcode(code);
        return;
      }
    } catch (error) {
      console.warn('BarcodeDetector error', error);
    }
  }

  requestAnimationFrame(scanFrame);
}

function stopScan() {
  stopQuagga();
  const videoWrapper = document.getElementById('videoWrapper');
  const scanVideo = document.getElementById('scanVideo');

  if (videoStream) {
    videoStream.getTracks().forEach(track => track.stop());
    videoStream = null;
  }
  if (scanVideo) scanVideo.srcObject = null;
  if (videoWrapper) videoWrapper.style.display = 'none';
}

function fillBarcode(code) {
  const input = document.getElementById(currentScanTarget);
  if (input) {
    input.value = code;
    input.focus();
  }
}

function openImageInput() {
  let fileInput = document.getElementById('scanImageInput');
  if (!fileInput) {
    fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/*';
    fileInput.capture = 'environment';
    fileInput.id = 'scanImageInput';
    fileInput.style.position = 'absolute';
    fileInput.style.left = '-9999px';
    fileInput.style.opacity = '0';
    fileInput.style.width = '1px';
    fileInput.style.height = '1px';
    fileInput.addEventListener('change', handleImageFile);
    document.body.appendChild(fileInput);
  }
  try {
    fileInput.value = '';
  } catch (e) {
    // some browsers disallow programmatic clearing, ignore
  }
  fileInput.click();
}

function handleImageFile(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) {
    return;
  }
  decodeImageFile(file);
}

function decodeImageFile(file) {
  if (!window.Quagga) {
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/@ericblade/quagga2/dist/quagga.min.js';
    script.onload = () => decodeImageFile(file);
    script.onerror = () => alert('无法加载扫码回退库，请手动输入条形码。');
    document.head.appendChild(script);
    return;
  }

  const resultEl = document.getElementById('scanResult');
  if (resultEl) resultEl.textContent = '正在识别图片，请稍候……';

  const img = new Image();
  const objectUrl = URL.createObjectURL(file);
  img.onload = async () => {
    try {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');

      // try different scales and rotations
      const attempts = [];
      const maxDim = 1200; // limit large images
      let w = img.naturalWidth;
      let h = img.naturalHeight;
      const scale = Math.min(1, maxDim / Math.max(w, h));
      w = Math.round(w * scale);
      h = Math.round(h * scale);

      // attempt auto-crop from the scaled full image first
      const baseCanvas = document.createElement('canvas');
      baseCanvas.width = w; baseCanvas.height = h;
      const baseCtx = baseCanvas.getContext('2d');
      baseCtx.drawImage(img, 0, 0, w, h);
      const crops = await autoCropImageFromCanvas(baseCanvas);

      const rotations = [0, 90, 270, 180];
      // if auto-crop produced crops, prepend them to attempts to try first
      if (crops && crops.length > 0) {
        for (const c of crops) attempts.push(c);
      }
      for (const rot of rotations) {
        // prepare canvas for rotation
        if (rot === 90 || rot === 270) {
          canvas.width = h;
          canvas.height = w;
        } else {
          canvas.width = w;
          canvas.height = h;
        }
        // draw with rotation
        ctx.save();
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (rot !== 0) {
          ctx.translate(canvas.width / 2, canvas.height / 2);
          ctx.rotate(rot * Math.PI / 180);
          ctx.drawImage(img, -w / 2, -h / 2, w, h);
        } else {
          ctx.drawImage(img, 0, 0, w, h);
        }
        ctx.restore();

        // simple contrast/brightness adjustment to help decoder
        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const data = imageData.data;
        // convert to grayscale and enhance contrast
        for (let i = 0; i < data.length; i += 4) {
          const r = data[i], g = data[i+1], b = data[i+2];
          const gray = (r * 0.299 + g * 0.587 + b * 0.114);
          // increase contrast around mid-tone
          const contrasted = Math.max(0, Math.min(255, (gray - 128) * 1.4 + 128));
          data[i] = data[i+1] = data[i+2] = contrasted;
        }
        ctx.putImageData(imageData, 0, 0);

        const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
        attempts.push(dataUrl);
      }

      // try decode attempts sequentially
      for (const src of attempts) {
        // eslint-disable-next-line no-await-in-loop
        const res = await new Promise(resolve => {
          Quagga.decodeSingle({
            src,
            numOfWorkers: 0,
            decoder: { readers: ['ean_reader','ean_8_reader','code_128_reader','code_39_reader','upc_reader'] },
            locate: true
          }, resolve);
        });
        if (res && res.codeResult && res.codeResult.code) {
          fillBarcode(res.codeResult.code);
          if (resultEl) resultEl.textContent = `识别成功：${res.codeResult.code}`;
          URL.revokeObjectURL(objectUrl);
          // clear preview state
          lastImageDataUrl = null;
          lastRotation = 0;
          closePreview();
          return;
        }
      }

      // if none succeeded, keep a preview and allow user to rotate/retry
      URL.revokeObjectURL(objectUrl);
      if (attempts && attempts.length > 0) {
        lastImageDataUrl = attempts[0];
        lastRotation = 0;
        setPreview(lastImageDataUrl);
        if (resultEl) resultEl.textContent = '识别失败，可旋转图片后重试。';
      } else {
        if (resultEl) resultEl.textContent = '';
        alert('图片识别失败，请确保条码完整、清晰、并尽量垂直拍摄后重试。');
      }
    } catch (err) {
      URL.revokeObjectURL(objectUrl);
      console.error('decodeImageFile error', err);
      if (resultEl) resultEl.textContent = '';
      alert('图片识别出错，请重试或手动输入条形码。');
    }
  };
  img.onerror = () => {
    URL.revokeObjectURL(objectUrl);
    alert('无法读取图片文件，请重试。');
  };
  img.src = objectUrl;
}

function setPreview(dataUrl) {
  const container = document.getElementById('scanPreviewContainer');
  const img = document.getElementById('scanPreview');
  if (img && container) {
    img.src = dataUrl;
    container.style.display = 'block';
  }
}

// Try to auto-crop likely barcode region from a canvas and return data URLs
async function autoCropImageFromCanvas(canvas) {
  try {
    const w = canvas.width, h = canvas.height;
    const ctx = canvas.getContext('2d');
    const imgData = ctx.getImageData(0, 0, w, h);
    const data = imgData.data;

    // Compute vertical edge strength per column (sum of abs horizontal differences)
    const colScores = new Float32Array(w);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w - 1; x++) {
        const i = (y * w + x) * 4;
        const r = data[i], g = data[i+1], b = data[i+2];
        const r2 = data[i+4], g2 = data[i+5], b2 = data[i+6];
        const gray = 0.299*r + 0.587*g + 0.114*b;
        const gray2 = 0.299*r2 + 0.587*g2 + 0.114*b2;
        colScores[x] += Math.abs(gray2 - gray);
      }
    }

    // Smooth scores with simple box filter
    const smooth = new Float32Array(w);
    const radius = Math.max(1, Math.round(w * 0.01));
    for (let x = 0; x < w; x++) {
      let sum = 0, cnt = 0;
      for (let k = -radius; k <= radius; k++) {
        const xi = x + k;
        if (xi >= 0 && xi < w) { sum += colScores[xi]; cnt++; }
      }
      smooth[x] = sum / Math.max(1, cnt);
    }

    // Find segments where score > threshold
    let mean = 0; for (let i=0;i<w;i++) mean += smooth[i]; mean /= w;
    let variance = 0; for (let i=0;i<w;i++) { const d = smooth[i]-mean; variance += d*d; } variance /= w;
    const std = Math.sqrt(variance);
    const thresh = mean + std * 0.5;

    let segments = [];
    let inSeg = false, segStart = 0;
    for (let x = 0; x < w; x++) {
      if (smooth[x] >= thresh) {
        if (!inSeg) { inSeg = true; segStart = x; }
      } else {
        if (inSeg) { inSeg = false; segments.push([segStart, x-1]); }
      }
    }
    if (inSeg) segments.push([segStart, w-1]);

    if (segments.length === 0) return [];

    // Choose largest segment width
    segments.sort((a,b) => (b[1]-b[0]) - (a[1]-a[0]));
    const [sx, ex] = segments[0];

    // For rows, compute sum of column differences within selected columns to find vertical bounds
    const colL = Math.max(0, sx - Math.round((ex-sx)*0.2));
    const colR = Math.min(w-1, ex + Math.round((ex-sx)*0.2));
    const rowScores = new Float32Array(h);
    for (let y = 0; y < h - 1; y++) {
      let sum = 0;
      for (let x = colL; x <= colR; x++) {
        const i = (y * w + x) * 4;
        const r = data[i], g = data[i+1], b = data[i+2];
        const i2 = ((y+1) * w + x) * 4;
        const r2 = data[i2], g2 = data[i2+1], b2 = data[i2+2];
        const gray = 0.299*r + 0.587*g + 0.114*b;
        const gray2 = 0.299*r2 + 0.587*g2 + 0.114*b2;
        sum += Math.abs(gray2 - gray);
      }
      rowScores[y] = sum;
    }

    // Smooth rows
    const rsmooth = new Float32Array(h);
    const rr = Math.max(1, Math.round(h * 0.01));
    for (let y = 0; y < h; y++) {
      let sum = 0, cnt = 0;
      for (let k = -rr; k <= rr; k++) {
        const yi = y + k;
        if (yi >= 0 && yi < h) { sum += rowScores[yi]; cnt++; }
      }
      rsmooth[y] = sum / Math.max(1, cnt);
    }

    let rmean = 0; for (let i=0;i<h;i++) rmean += rsmooth[i]; rmean /= h;
    let rvar = 0; for (let i=0;i<h;i++){ const d = rsmooth[i]-rmean; rvar += d*d; } rvar/=h;
    const rstd = Math.sqrt(rvar);
    const rthresh = rmean + rstd * 0.3;

    let rsegments = [], rin=false, rstart=0;
    for (let y=0;y<h;y++){
      if (rsmooth[y] >= rthresh) { if(!rin){ rin=true; rstart=y; } }
      else { if(rin){ rin=false; rsegments.push([rstart,y-1]); } }
    }
    if (rin) rsegments.push([rstart,h-1]);
    if (rsegments.length === 0) return [];

    rsegments.sort((a,b)=>(b[1]-b[0])-(a[1]-a[0]));
    const [sy, ey] = rsegments[0];

    // add padding
    const padX = Math.round((ex - sx) * 0.2) + 10;
    const padY = Math.round((ey - sy) * 0.2) + 10;
    const cx1 = Math.max(0, sx - padX);
    const cx2 = Math.min(w-1, ex + padX);
    const cy1 = Math.max(0, sy - padY);
    const cy2 = Math.min(h-1, ey + padY);

    const cropW = cx2 - cx1 + 1;
    const cropH = cy2 - cy1 + 1;
    if (cropW < 30 || cropH < 30) return [];

    const cropCanvas = document.createElement('canvas');
    cropCanvas.width = cropW;
    cropCanvas.height = cropH;
    const cctx = cropCanvas.getContext('2d');
    cctx.drawImage(canvas, cx1, cy1, cropW, cropH, 0, 0, cropW, cropH);
    const dataUrl = cropCanvas.toDataURL('image/jpeg', 0.95);
    return [dataUrl];
  } catch (e) {
    console.warn('autoCropImageFromCanvas failed', e);
    return [];
  }
}

function closePreview() {
  const container = document.getElementById('scanPreviewContainer');
  const img = document.getElementById('scanPreview');
  const resultEl = document.getElementById('scanResult');
  if (img) img.src = '';
  if (container) container.style.display = 'none';
  if (resultEl) resultEl.textContent = '';
  lastImageDataUrl = null;
  lastRotation = 0;
}

async function decodeFromDataUrl(dataUrl) {
  return new Promise(resolve => {
    Quagga.decodeSingle({
      src: dataUrl,
      numOfWorkers: 0,
      decoder: { readers: ['ean_reader','ean_8_reader','code_128_reader','code_39_reader','upc_reader'] },
      locate: true
    }, resolve);
  });
}

async function rotatePreview(angle) {
  if (!lastImageDataUrl) return;
  lastRotation = (lastRotation + angle + 360) % 360;
  // draw image to canvas with rotation
  const img = document.createElement('img');
  img.src = lastImageDataUrl;
  await new Promise((res, rej) => { img.onload = res; img.onerror = rej; });
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  let w = img.naturalWidth, h = img.naturalHeight;
  const rot = lastRotation % 360;
  if (rot === 90 || rot === 270) {
    canvas.width = h; canvas.height = w;
    ctx.translate(canvas.width/2, canvas.height/2);
    ctx.rotate(rot * Math.PI/180);
    ctx.drawImage(img, -w/2, -h/2, w, h);
  } else {
    canvas.width = w; canvas.height = h;
    ctx.translate(canvas.width/2, canvas.height/2);
    ctx.rotate(rot * Math.PI/180);
    ctx.drawImage(img, -w/2, -h/2, w, h);
  }
  const newDataUrl = canvas.toDataURL('image/jpeg', 0.9);
  lastImageDataUrl = newDataUrl;
  setPreview(newDataUrl);
}

async function retryPreview() {
  if (!lastImageDataUrl) return;
  const resultEl = document.getElementById('scanResult');
  if (resultEl) resultEl.textContent = '重新识别中……';
  const res = await decodeFromDataUrl(lastImageDataUrl);
  if (res && res.codeResult && res.codeResult.code) {
    fillBarcode(res.codeResult.code);
    if (resultEl) resultEl.textContent = `识别成功：${res.codeResult.code}`;
    closePreview();
  } else {
    if (resultEl) resultEl.textContent = '识别失败，请尝试旋转图片或更换拍摄角度。';
  }
}

async function scanCashierBarcode() {
  const barcodeInput = document.getElementById('cashierBarcode');
  const resultEl = document.getElementById('scanResult');
  const barcode = barcodeInput.value.trim();
  resultEl.textContent = '';
  if (!barcode) {
    resultEl.textContent = '请输入条形码后再添加。';
    return;
  }

  const response = await fetch('/api/cashier/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ barcode }),
  });

  const data = await response.json();
  if (!response.ok) {
    resultEl.textContent = data.error || '添加商品失败';
    return;
  }

  resultEl.textContent = `已加入：${data.product.name} ¥${data.product.price.toFixed(2)}，数量 ${data.product.qty}`;
  updateCartTable(data.cart.items, data.cart.total);
  barcodeInput.value = '';
}

function updateCartTable(items, total) {
  const body = document.getElementById('cartBody');
  const totalEl = document.getElementById('cartTotal');
  const payableEl = document.getElementById('cartPayable');
  body.innerHTML = '';

  if (!items || items.length === 0) {
    body.innerHTML = '<tr><td colspan="5">购物车为空</td></tr>';
  } else {
    for (const item of items) {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td>${item.barcode}</td>
        <td>${item.name}</td>
        <td>¥${item.price.toFixed(2)}</td>
        <td>${item.qty}</td>
        <td>¥${item.subtotal.toFixed(2)}</td>
      `;
      body.appendChild(row);
    }
  }
  if (totalEl) totalEl.textContent = total.toFixed(2);
  if (payableEl) payableEl.textContent = applyDiscount(total).toFixed(2);
}

async function verifyMember() {
  const memberId = document.getElementById('memberId').value.trim();
  const memberInfo = document.getElementById('memberInfo');

  if (!memberId) {
    memberInfo.textContent = '请输入会员卡号进行验证。';
    return;
  }

  const response = await fetch(`/api/member/${encodeURIComponent(memberId)}`);
  const data = await response.json();
  if (!response.ok) {
    memberInfo.textContent = data.error || '会员验证失败';
    currentMember = null;
    updateTotals();
    return;
  }
  currentMember = data.member;
  memberInfo.textContent = `会员：${currentMember.name}，折扣 ${currentMember.discount}% 已应用。`;
  updateTotals();
}

function clearMember() {
  currentMember = null;
  const mid = document.getElementById('memberId');
  if (mid) mid.value = '';
  const memberInfo = document.getElementById('memberInfo');
  if (memberInfo) memberInfo.textContent = '当前未应用会员折扣。';
  updateTotals();
}

function applyDiscount(total) {
  const m = currentMember;
  if (!m || !m.discount) return total;
  return total * (1 - m.discount / 100);
}

function updateTotals() {
  const totalEl = document.getElementById('cartTotal');
  const payableEl = document.getElementById('cartPayable');
  const currentTotal = parseFloat(totalEl ? totalEl.textContent : '0') || 0;
  if (payableEl) payableEl.textContent = applyDiscount(currentTotal).toFixed(2);
}

function buildReceipt(items, total) {
  const discountText = currentMember ? `${currentMember.discount}%` : '无';
  const payable = applyDiscount(total).toFixed(2);
  const date = new Date().toLocaleString();
  const lines = items.map(item => `
    <tr>
      <td>${item.name}</td>
      <td>${item.qty}</td>
      <td>¥${item.price.toFixed(2)}</td>
      <td>¥${item.subtotal.toFixed(2)}</td>
    </tr>
  `).join('');
  return `
    <html>
      <head>
        <title>小票</title>
        <style>
          body { font-family: Arial, sans-serif; padding: 20px; }
          h2 { margin-top: 0; }
          table { width: 100%; border-collapse: collapse; margin-top: 12px; }
          td, th { border: 1px solid #ccc; padding: 8px; text-align: left; }
          .summary { margin-top: 16px; font-size: 1.1em; }
        </style>
      </head>
      <body>
        <h2>收银小票</h2>
        <p>时间：${date}</p>
        <p>会员：${currentMember ? currentMember.name : '无'}（折扣 ${discountText}）</p>
        <table>
          <thead>
            <tr><th>商品</th><th>数量</th><th>单价</th><th>小计</th></tr>
          </thead>
          <tbody>
            ${lines}
          </tbody>
        </table>
        <div class="summary">
          <p>原总价：¥${total.toFixed(2)}</p>
          <p>折后价：¥${payable}</p>
        </div>
      </body>
    </html>
  `;
}

function printReceipt() {
  const items = [];
  document.querySelectorAll('#cartBody tr').forEach(row => {
    const cols = row.querySelectorAll('td');
    if (cols.length === 5) {
      items.push({
        name: cols[1].textContent.trim(),
        qty: parseFloat(cols[3].textContent.trim()) || 0,
        price: parseFloat(cols[2].textContent.replace('¥', '').trim()) || 0,
        subtotal: parseFloat(cols[4].textContent.replace('¥', '').trim()) || 0,
      });
    }
  });
  const total = parseFloat(document.getElementById('cartTotal').textContent || '0') || 0;
  const receiptWindow = window.open('', 'receipt');
  if (!receiptWindow) {
    alert('请允许弹出窗口以打印小票。');
    return;
  }
  receiptWindow.document.write(buildReceipt(items, total));
  receiptWindow.document.close();
  receiptWindow.focus();
  receiptWindow.print();
}

async function checkout() {
  if (!confirm('确认结账并扣减库存吗？')) return;
  const memberId = document.getElementById('memberId') ? document.getElementById('memberId').value.trim() : '';
  const response = await fetch('/api/cashier/checkout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ member_id: memberId }),
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.error || '结账失败');
    return;
  }
  alert(data.message || '结账完成');
  window.location.reload();
}

async function cancelCart() {
  if (!confirm('确认取消本次购物车内容吗？')) return;
  const response = await fetch('/api/cashier/cancel', { method: 'POST' });
  if (response.ok) {
    window.location.reload();
  }
}

// Global error handler to help debugging in mobile browsers
window.addEventListener('error', function(e) {
  try {
    const el = document.getElementById('scanResult');
    if (el) el.textContent = '脚本错误: ' + (e && e.message ? e.message : String(e));
  } catch (ex) {}
});

function printReceipt() {
  const items = [];
  document.querySelectorAll('#cartBody tr').forEach(row => {
    const cols = row.querySelectorAll('td');
    if (cols.length === 5) {
      items.push({
        name: cols[1].textContent.trim(),
        qty: parseFloat(cols[3].textContent.trim()) || 0,
        price: parseFloat(cols[2].textContent.replace('¥', '').trim()) || 0,
        subtotal: parseFloat(cols[4].textContent.replace('¥', '').trim()) || 0,
      });
    }
  });
  const total = parseFloat(document.getElementById('cartTotal').textContent || '0') || 0;
  const receiptWindow = window.open('', 'receipt');
  if (!receiptWindow) {
    alert('请允许弹出窗口以打印小票。');
    return;
  }
  receiptWindow.document.write(buildReceipt(items, total));
  receiptWindow.document.close();
  receiptWindow.focus();
  receiptWindow.print();
}

async function checkout() {
  if (!confirm('确认结账并扣减库存吗？')) return;
  const memberId = document.getElementById('memberId').value.trim();
  const response = await fetch('/api/cashier/checkout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ member_id: memberId }),
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.error || '结账失败');
    return;
  }
  alert(data.message || '结账完成');
  window.location.reload();
}

async function cancelCart() {
  if (!confirm('确认取消本次购物车内容吗？')) return;
  const response = await fetch('/api/cashier/cancel', { method: 'POST' });
  if (response.ok) {
    window.location.reload();
  }
}
