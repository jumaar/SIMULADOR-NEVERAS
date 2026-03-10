/**
 * Dashboard del Simulador de Neveras Vorak Edge
 * =============================================
 * Este archivo contiene la lógica del frontend para el dashboard interactivo.
 * Nota: La implementación actual está embebida en templates/index.html para 
 * simplificar el despliegue. Este archivo sirve como referencia y para posibles
 * expansiones futuras.
 * 
 * Versión: 1.0.0
 * Autor: Vorak Edge Team
 */

(function() {
    'use strict';

    // Constantes de la API
    const API_BASE = '';
    const API_TIMEOUT = 30000;

    // Utilidades
    const api = {
        async request(endpoint, options = {}) {
            const url = `${API_BASE}${endpoint}`;
            const config = {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            };

            try {
                const response = await fetch(url, config);
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.error || `HTTP ${response.status}`);
                }
                
                return data;
            } catch (error) {
                console.error(`API Error [${endpoint}]:`, error);
                throw error;
            }
        },

        get(endpoint) {
            return this.request(endpoint, { method: 'GET' });
        },

        post(endpoint, body) {
            return this.request(endpoint, { method: 'POST', body: JSON.stringify(body) });
        },

        put(endpoint, body) {
            return this.request(endpoint, { method: 'PUT', body: JSON.stringify(body) });
        },

        delete(endpoint) {
            return this.request(endpoint, { method: 'DELETE' });
        }
    };

    // Servicios
    const FridgeService = {
        async getAll() {
            return api.get('/api/fridges');
        },

        async get(fridgeId) {
            return api.get(`/api/fridges/${fridgeId}`);
        },

        async create(password, location) {
            return api.post('/api/fridges', {
                password: password,
                location: location
            });
        },

        async updateTemperature(fridgeId, temperature) {
            return api.put(`/api/fridges/${fridgeId}/temperature`, { temperature });
        },

        async toggleDoor(fridgeId, isOpen) {
            return api.put(`/api/fridges/${fridgeId}/door`, { is_door_open: isOpen });
        },

        async sync(fridgeId) {
            return api.post(`/api/fridges/${fridgeId}/sync`);
        },

        async delete(fridgeId) {
            return api.delete(`/api/fridges/${fridgeId}`);
        }
    };

    const ProductService = {
        async getAll(fridgeId) {
            return api.get(`/api/fridges/${fridgeId}/products`);
        },

        async add(fridgeId, product) {
            return api.post(`/api/fridges/${fridgeId}/products`, product);
        },

        async update(fridgeId, ean, quantity) {
            return api.put(`/api/fridges/${fridgeId}/products/${ean}`, { quantity });
        },

        async delete(fridgeId, ean) {
            return api.delete(`/api/fridges/${fridgeId}/products/${ean}`);
        }
    };

    const EventService = {
        async getHistory(fridgeId, limit = 50) {
            return api.get(`/api/events?fridge_id=${fridgeId}&limit=${limit}`);
        }
    };

    // Utilidades UI
    const UI = {
        showLoading(message = 'Cargando...') {
            const overlay = document.querySelector('.loading-overlay');
            if (overlay) {
                const messageEl = overlay.querySelector('h4');
                if (messageEl) messageEl.textContent = message;
                overlay.style.display = 'flex';
            }
        },

        hideLoading() {
            const overlay = document.querySelector('.loading-overlay');
            if (overlay) {
                overlay.style.display = 'none';
            }
        },

        showError(message) {
            const alertEl = document.querySelector('.alert-danger');
            if (alertEl) {
                alertEl.textContent = message;
                alertEl.style.display = 'block';
                setTimeout(() => {
                    alertEl.style.display = 'none';
                }, 5000);
            }
        },

        formatDate(dateStr) {
            if (!dateStr) return '-';
            return new Date(dateStr).toLocaleString('es-CO', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        },

        formatTemperature(temp) {
            return `${temp.toFixed(1)}°C`;
        }
    };

    // Exportar al namespace global
    window.VorakSimulator = {
        api,
        services: {
            fridge: FridgeService,
            product: ProductService,
            event: EventService
        },
        ui: UI,
        utils: {
            formatDate: UI.formatDate,
            formatTemperature: UI.formatTemperature
        }
    };

})();
