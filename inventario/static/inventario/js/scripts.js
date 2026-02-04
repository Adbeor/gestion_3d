/* ==========================================
   SCRIPTS.JS - Logica Global de la Aplicación
   ========================================== */

document.addEventListener("DOMContentLoaded", () => {
    
    // ==========================================
    // 0. UTILIDADES GLOBALES
    // ==========================================
    
    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    // Contexto de Pagina (Si existe)
    const contextEl = document.getElementById('page-context');
    const productoId = contextEl ? contextEl.dataset.productoId : null;

    // ==========================================
    // 1. UI INTERACCIONES (Popovers)
    // ==========================================
    const triggers = document.querySelectorAll('.hover-trigger');
    triggers.forEach(trigger => {
        trigger.addEventListener('mouseenter', function () {
            const popover = this.querySelector('.popover-imagen');
            if (!popover) return; 
            
            const rect = this.getBoundingClientRect();
            // Mantener lógica original: techo < 250px -> mostrar abajo
            if (rect.top < 250) {
                popover.classList.add('mostrar-abajo');
            } else {
                popover.classList.remove('mostrar-abajo');
            }
        });
    });

    // ==========================================
    // 2. EXPORTAR FUNCIONES A WINDOW (Para onclicks)
    // ==========================================

    window.mostrarMensaje = function(id, msg, color) {
        const el = document.querySelector(`.msg-${id}`);
        if(el) {
            el.textContent = msg;
            el.style.color = color || "#27ae60";
            setTimeout(() => el.textContent = "", 3000);
        }
    };

    window.actualizarInterfaz = function(id, nuevoStock) {
        // A. Stock Texto
        const stockEl = document.getElementById(`stock-display-${id}`);
        if(stockEl) stockEl.textContent = `${nuevoStock} u.`;

        // B. Equivalencia
        const equivTextComp = document.getElementById(`equiv-text-${id}`);
        if (!equivTextComp) return; 

        const equivCell = equivTextComp.closest('td');
        const requerido = parseFloat(equivCell.getAttribute('data-requerido')) || 0;
        
        let equiv = 0;
        let pct = 0;

        if (requerido > 0) {
            equiv = nuevoStock / requerido;
            pct = Math.min(equiv * 100, 100);
        }

        equivTextComp.textContent = `${equiv.toFixed(1)}`;

        // C. Barra
        const barra = document.getElementById(`barra-fill-${id}`);
        if(barra) barra.style.width = `${pct}%`;

        // D. Viabilidad
        checkViability();
    };

    window.checkViability = function() {
        let esViable = true;
        
        const celdas = document.querySelectorAll('td[data-requerido]');
        celdas.forEach(td => {
            const req = parseFloat(td.getAttribute('data-requerido')) || 0;
            const spanId = td.querySelector('span').id; // equiv-text-{ID}
            const piezaId = spanId.split('-')[2];
            
            const stockInput = document.querySelector(`.input-stock-${piezaId}`);
            if (stockInput) {
                const stock = parseFloat(stockInput.value) || 0;
                if (stock < req) esViable = false;
            }
        });

        const header = document.getElementById('viability-header');
        const text = document.getElementById('viability-text');
        const btnArmar = document.getElementById('form-armar');

        if(header && text) {
            if(esViable) {
                header.innerHTML = "✅ Producción Viable";
                header.style.color = "#27ae60";
                text.textContent = "Tienes todas las piezas impresas necesarias.";
                if(btnArmar) btnArmar.style.display = "block";
            } else {
                header.innerHTML = "⚠️ Producción Detenida";
                header.style.color = "#e74c3c";
                text.textContent = "Faltan imprimir piezas para poder armar.";
                if(btnArmar) btnArmar.style.display = "none";
            }
        }
    };

    // ==========================================
    // 3. API CALLS
    // ==========================================

    window.imprimirPieza = async function(id, btn) {
        if(btn) btn.disabled = true;
        try {
            const res = await fetch(`/inventario/api/stock-pieza/${id}/`, {
                method: 'POST',
                body: JSON.stringify({ accion: 'imprimir', cantidad: 1 }),
                headers: {'X-CSRFToken': getCsrfToken()}
            });
            const data = await res.json();
            
            if(data.status === 'ok') {
                const input = document.querySelector(`.input-stock-${id}`);
                if(input) input.value = data.nuevo_stock;
                
                mostrarMensaje(id, "✅ Impresa (+1)");
                actualizarInterfaz(id, data.nuevo_stock);
            } else {
                mostrarMensaje(id, "❌ " + data.mensaje, "red");
            }
        } catch(e) { console.error(e); }
        if(btn) btn.disabled = false;
    };

    window.updateStock = async function(id, delta, btn) {
        try {
            const res = await fetch(`/inventario/api/stock-pieza/${id}/`, {
                method: 'POST',
                body: JSON.stringify({ accion: 'ajustar', cantidad: delta }),
                headers: {'X-CSRFToken': getCsrfToken()}
            });
            const data = await res.json();
            if(data.status === 'ok') {
                const input = document.querySelector(`.input-stock-${id}`);
                if(input) input.value = data.nuevo_stock;

                mostrarMensaje(id, delta > 0 ? "✅ Agregado" : "⚠️ Descontado");
                actualizarInterfaz(id, data.nuevo_stock);
            }
        } catch(e) { console.error(e); }
    };

    window.setStock = async function(id, valor, input) {
        try {
            const res = await fetch(`/inventario/api/stock-pieza/${id}/`, {
                method: 'POST',
                body: JSON.stringify({ accion: 'fijar', cantidad: valor }),
                headers: {'X-CSRFToken': getCsrfToken()}
            });
            const data = await res.json();
            if(data.status === 'ok') {
                input.value = data.nuevo_stock; 
                mostrarMensaje(id, "✅ Stock fijado");
                actualizarInterfaz(id, data.nuevo_stock); 
            }
        } catch(e) { console.error(e); }
    };

    // ==========================================
    // 4. CREACIONES (Filamentos, Insumos)
    // ==========================================

    window.crearFilamento = async function() {
        const tipoEl = document.getElementById('new-fil-tipo');
        const colorEl = document.getElementById('new-fil-color');
        if(!tipoEl || !colorEl) return;
        
        const tipo = tipoEl.value;
        const color = colorEl.value;
        
        if(!tipo || !color) return alert("Escribe tipo y color");

        try {
            const res = await fetch('/inventario/api/crear-filamento/', {
                method: 'POST',
                body: JSON.stringify({ tipo: tipo, color: color }),
                headers: {'X-CSRFToken': getCsrfToken()}
            });
            const data = await res.json();
            if(data.status === 'ok') {
                const select = document.getElementById('select-material');
                if(select) {
                    const opt = document.createElement('option');
                    opt.value = data.id;
                    opt.textContent = data.text;
                    opt.selected = true;
                    select.appendChild(opt);
                }
                const form = document.getElementById('form-nuevo-filamento');
                if(form) form.style.display='none';
            } else {
                alert("Error: " + data.mensaje);
            }
        } catch(e) { console.error(e); }
    };

    window.vincularInsumo = async function() {
        const select = document.getElementById('select-insumo');
        const cant = document.getElementById('cant-insumo');
        const check = document.getElementById('check-opcional');
        
        if(!select || !productoId) return;

        const insumoId = select.value;
        if(!insumoId) return alert("Selecciona un insumo");

        try {
            const res = await fetch(`/inventario/api/vincular-insumo/${productoId}/`, {
                method: 'POST',
                body: JSON.stringify({ 
                    insumo_id: insumoId, 
                    cantidad: cant.value,
                    es_opcional: check.checked 
                }),
                headers: {'X-CSRFToken': getCsrfToken()}
            });
            const data = await res.json();
            if(data.status === 'ok') location.reload();
            else alert(data.mensaje);
        } catch(e) { console.error(e); }
    };

    window.crearInsumoExpress = async function() {
        const nombre = document.getElementById('new-nom-ins').value;
        const unidad = document.getElementById('new-und-ins').value || 'unidad';
        const costo = document.getElementById('new-cost-ins').value || 0;

        if(!nombre) return alert("Falta nombre");

        try {
            const res = await fetch('/inventario/api/crear-insumo/', {
                method: 'POST',
                body: JSON.stringify({ nombre, unidad, costo }),
                headers: {'X-CSRFToken': getCsrfToken()}
            });
            const data = await res.json();
            if(data.status === 'ok') location.reload(); 
            else alert(data.mensaje);
        } catch(e) { console.error(e); }
    };

});
