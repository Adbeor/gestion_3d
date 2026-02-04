# Gestión 3D - Sistema de Inventario y Producción

Sistema integral para la gestión de impresión 3D, inventario de filamentos, piezas y productos.

## 🚀 Características Principales

### 📦 Gestión de Inventario
- **Filamentos**: Control detallado de rollos (Stock, Colores, Tipos).
- **Insumos**: Gestión de componentes externos (Imanes, tornillos, rodamientos, motores).
- **Piezas**: Registro de piezas impresas con asociación automática de archivos GCode.

### 💰 Análisis de Costos y Rentabilidad
- Cálculo automático de costos de producción basado en:
    - Peso de filamento (gramos).
    - Costo del rollo.
    - Costo de insumos externos.
- Visualización de márgenes de ganancia en tiempo real.
- Alertas de viabilidad de producción según stock actual.

### 🖨️ Integración con Archivos de Impresión
- **Soporte Avanzado de GCode**:
    - Extracción automática de Peso y Tiempo de impresión.
    - Generación de Thumbnails (Previsualizaciones).
- **Soporte Bambu Lab / Orca Slicer (.3mf)**:
    - Lectura inteligente de archivos `.3mf` (formato Zip).
    - Extracción de metadata precisa (`slice_info.config`) para peso y tiempo.

### 🛠️ Flujo de Trabajo
- **Kanban de Proyectos**: Visualización del estado de pedidos y proyectos.
- **Producción Dinámica**: 
    - Crear piezas "Express" directamente desde la vista de producto.
    - Vincular insumos y piezas con un solo clic.
    - Verificación instantánea de "Armado Disponible" y piezas faltantes.

## 💻 Tecnologías
- **Backend**: Django (Python)
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Base de Datos**: SQLite (Dev)

## 📋 Changelog Reciente
- **Febrero 2026**:
    - Agregado soporte para archivos `.3mf` (Bambu Lab) con lectura de metadata XML.
    - Implementado sistema de Insumos (Componentes no impresos).
    - Mejoras en la interfaz de detalle de producto (Tablas dinámicas, formularios express).
    - Corrección de cálculo de tiempos de impresión ("3m" vs ".3mf").
    - Refactorización de estilos a archivos estáticos CSS.
