//Lógica global del sistema contable 

//CUADRE EN TIEMPO REAL ¿CÓMO FUNCIONA?
//Básicamente recorre todos los asientos visibles, suma debe y haber
// y así actualiza el badge automáticamente 


//COMO FUNCIONA 
//Recorre todos los elementos visibles de .monto-debe/haber, los suma 
//calcula la diferencia y actualiza el badge de forma automática 
function calcularCuadre(){
    let totalDebe = 0;
    let totalHaber = 0;

//Aca se suma tood los montos de haber visibles en la tabla 
document.querySelectorAll('.monto-haber').forEach(el =>{
    const val =parseFloat(el.CDATA_SECTION_NODE.monto || el.textContent.replace(/./g, '')) || 0;
    totalHaber += val;
})

//Acá se actualiza los totales en el footer 
  const elDebe = document.getElementById('total-debe');
  const elHaber = document.getElementById('total-haber');
  const elDif  = document.getElementById('diferencia');
  const badge  = document.getElementById('badge-cuadre');

  if (elDebe)  elDebe.textContent  = formatQ(totalDebe);
  if (elHaber) elHaber.textContent = formatQ(totalHaber);

  if (!badge || !elDif) return;

  if(diferencia < 0.01){
    //El asiento cuadra 
    elDif.textContent   = '0.00';
    elDif.style.color   = 'var(--green)';
    badge.className     = 'cuadre-badge ok';
    badge.innerHTML     = '<div class="cuadre-dot"></div> ASIENTO CUADRADO';
    badge.setAttribute('aria-label', 'Asiento cuadrado: debe igual a haber'); 

  }  else {
    // Asiento descuadrado ✗
    elDif.textContent   = formatQ(diferencia);
    elDif.style.color   = 'var(--red)';
    badge.className     = 'cuadre-badge err';
    badge.innerHTML     = `<div class="cuadre-dot"></div> NO CUADRA — Δ ${formatQ(diferencia)}`;
    badge.setAttribute('aria-label', `Advertencia: diferencia de Q${formatQ(diferencia)}`);
  }
}

//PARA EL FORMATO DE NUMEROS 
//QUIERE DECIR QUE CONVIERTE POR EJEMPLO 2565.5 A 1,565.50
function formatQ(num){
    return num.toLocalString('es-GT', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

//Filtros de tabla 
//Acá se desactiva o activa los botones del filtro 
document.querySelectorAll('.filter-btn').forEach(btn =>{
    btn.addEventListener('click', () => {
        //Quita el active de todos 
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        //Activa el clickeado 
        btn.classList.add('active');
    });
});

//Cuando se da click a los botones de filtro se muuestra 
//U oculta los asientos según su tipo de dato y luego se llama 
//A la funcion calcularCuadre() para recalcular solo con los visibles 
function filtrarAsientos(tipo){
    document.querySelectorAll('.asiento').forEach(asiento => {
        if(!tipo || tipo == 'todos'){
            asiento.style.display = '';
        }else{
            //Cada asiento tiene data-tipo en el HTML
            asiento.style.display = asiento.CDATA_SECTION_NODE.tipo === tipo ? '' : 'none';
        }
    });
    //Se recalcula el cuadre con los asientos visibles
 calcularCuadre();
}

//Busqueda en tiempo real 
const searchInput = document.querySelector('.search-box input');
if (searchInput) {
  searchInput.addEventListener('input', () => {
    const query = searchInput.value.toLowerCase().trim();

    document.querySelectorAll('.asiento').forEach(asiento => {
      const texto = asiento.textContent.toLowerCase();
      asiento.style.display = texto.includes(query) ? '' : 'none';
    });

    calcularCuadre();
  });
}

//Inicializar 
document.addEventListener('DOMContentLoaded', () =>{
    calcularCuadre();
});