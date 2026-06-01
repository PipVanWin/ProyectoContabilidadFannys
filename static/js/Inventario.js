// inventario.js

// ── TABS ──────────────────────────────────────────────────
function cambiarTab(btn) {
  document.querySelectorAll('.filter-btn[data-tab]').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');

  document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
  document.getElementById('tab-' + btn.dataset.tab).style.display = '';
}

// ── BÚSQUEDA ──────────────────────────────────────────────
document.getElementById('search-inv').addEventListener('input', function() {
  const q = this.value.toLowerCase();
  document.querySelectorAll('.inv-row').forEach(row => {
    row.style.display = row.dataset.nombre.includes(q) ? '' : 'none';
  });
});

// ── MODAL ─────────────────────────────────────────────────
function abrirModal(tipo) {
  document.getElementById('modal-overlay').style.display = 'grid';
}

function cerrarModal() {
  document.getElementById('modal-overlay').style.display = 'none';
}

function seleccionarTipo(btn) {
  document.querySelectorAll('.filter-btn[data-tipo]').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

// ── GUARDAR ITEM ──────────────────────────────────────────
async function guardarItem() {
  const tipo     = document.querySelector('.filter-btn[data-tipo].active').dataset.tipo;
  const nombre   = document.getElementById('f-nombre').value.trim();
  const codigo   = document.getElementById('f-codigo').value.trim();
  const categoria= document.getElementById('f-categoria').value.trim();
  const costo    = parseFloat(document.getElementById('f-costo').value) || 0;
  const precio   = parseFloat(document.getElementById('f-precio').value) || 0;
  const cantidad = parseInt(document.getElementById('f-cantidad').value) || 0;
  const unidad   = document.getElementById('f-unidad').value.trim();

  if (!nombre) {
    alert('El nombre es obligatorio');
    return;
  }

  const response = await fetch('/inventario/nuevo', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tipo, nombre, codigo, categoria,
                           costo_unitario: costo, precio_venta: precio,
                           cantidad, unidad })
  });

  if (response.ok) {
    cerrarModal();
    location.reload();
  } else {
    alert('Error al guardar. Intenta de nuevo.');
  }
}

// ── IMPORTAR EXCEL ────────────────────────────────────────
async function importarExcel(input) {
  const file = input.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('archivo', file);

  const response = await fetch('/inventario/importar-excel', {
    method: 'POST',
    body: formData
  });

  if (response.ok) {
    const data = await response.json();
    alert(`✓ Se importaron ${data.importados} items correctamente`);
    location.reload();
  } else {
    alert('Error al importar el archivo. Verifica el formato.');
  }
}