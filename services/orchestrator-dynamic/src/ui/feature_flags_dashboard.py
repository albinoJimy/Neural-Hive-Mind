"""
Feature Flags Dashboard UI - Router FastAPI.

Fornece interface web para gestão de feature flags dinâmicas.
Serve HTML estático e endpoints JSON para operações CRUD.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# =============================================================================
# Pydantic Schemas
# =============================================================================


class DashboardFlagCreate(BaseModel):
    """Schema para criação de flag via dashboard."""

    flag_name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    enabled: bool = Field(default=False)
    rollout_strategy: str = Field(default="all")
    rollout_config: dict = Field(default_factory=dict)
    created_by: str = Field(default="dashboard-user", max_length=100)
    owner: str | None = Field(None, max_length=100)
    tags: list[str] = Field(default_factory=list)


class DashboardFlagUpdate(BaseModel):
    """Schema para atualização de flag via dashboard."""

    description: str | None = Field(None, max_length=500)
    enabled: bool | None = None
    rollout_strategy: str | None = Field(None)
    rollout_config: dict | None = None
    owner: str | None = Field(None, max_length=100)
    tags: list[str] | None = None


class ToggleResponse(BaseModel):
    """Resposta de toggle."""

    flag_name: str
    enabled: bool
    previous_state: bool
    message: str


class ErrorResponse(BaseModel):
    """Resposta de erro."""

    error: str
    detail: str | None = None


# =============================================================================
# Templates HTML
# =============================================================================


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Feature Flags Dashboard - Neural Hive Mind</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        .header {
            margin-bottom: 30px;
            padding: 20px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            backdrop-filter: blur(10px);
        }

        .header h1 {
            font-size: 28px;
            font-weight: 600;
            margin-bottom: 8px;
            background: linear-gradient(90deg, #64b5f6, #81c784);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .header p {
            color: #9e9e9e;
            font-size: 14px;
        }

        .toolbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 15px;
        }

        .search-box {
            flex: 1;
            max-width: 400px;
        }

        .search-box input {
            width: 100%;
            padding: 12px 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            color: #e0e0e0;
            font-size: 14px;
            transition: all 0.3s ease;
        }

        .search-box input:focus {
            outline: none;
            border-color: #64b5f6;
            background: rgba(100, 181, 246, 0.1);
        }

        .filters {
            display: flex;
            gap: 10px;
            align-items: center;
        }

        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .btn-primary {
            background: linear-gradient(135deg, #64b5f6, #42a5f5);
            color: white;
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(100, 181, 246, 0.4);
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.1);
            color: #e0e0e0;
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.15);
        }

        .btn-success {
            background: linear-gradient(135deg, #81c784, #66bb6a);
            color: white;
        }

        .btn-danger {
            background: linear-gradient(135deg, #e57373, #ef5350);
            color: white;
        }

        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }

        .stat-card {
            padding: 20px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            backdrop-filter: blur(10px);
        }

        .stat-card .label {
            font-size: 12px;
            color: #9e9e9e;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }

        .stat-card .value {
            font-size: 32px;
            font-weight: 600;
            color: #e0e0e0;
        }

        .flags-table {
            background: rgba(255, 255, 255, 0.03);
            border-radius: 12px;
            overflow: hidden;
            backdrop-filter: blur(10px);
        }

        .flags-table table {
            width: 100%;
            border-collapse: collapse;
        }

        .flags-table th {
            padding: 15px 20px;
            text-align: left;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #9e9e9e;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        .flags-table td {
            padding: 15px 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .flags-table tr:hover {
            background: rgba(255, 255, 255, 0.02);
        }

        .badge {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .badge-enabled {
            background: rgba(129, 199, 132, 0.2);
            color: #81c784;
        }

        .badge-disabled {
            background: rgba(229, 115, 115, 0.2);
            color: #e57373;
        }

        .badge-strategy {
            background: rgba(100, 181, 246, 0.2);
            color: #64b5f6;
        }

        .toggle-switch {
            position: relative;
            width: 44px;
            height: 24px;
        }

        .toggle-switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .toggle-slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: rgba(255, 255, 255, 0.1);
            transition: 0.4s;
            border-radius: 24px;
        }

        .toggle-slider:before {
            position: absolute;
            content: "";
            height: 18px;
            width: 18px;
            left: 3px;
            bottom: 3px;
            background-color: white;
            transition: 0.4s;
            border-radius: 50%;
        }

        input:checked + .toggle-slider {
            background: linear-gradient(135deg, #81c784, #66bb6a);
        }

        input:checked + .toggle-slider:before {
            transform: translateX(20px);
        }

        .actions {
            display: flex;
            gap: 8px;
        }

        .btn-icon {
            padding: 6px 12px;
            font-size: 12px;
        }

        .loading {
            text-align: center;
            padding: 40px;
            color: #9e9e9e;
        }

        .error {
            background: rgba(229, 115, 115, 0.1);
            border: 1px solid rgba(229, 115, 115, 0.3);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            color: #e57373;
        }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #9e9e9e;
        }

        .empty-state svg {
            width: 64px;
            height: 64px;
            margin-bottom: 15px;
            opacity: 0.5;
        }

        /* Modal */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.7);
            backdrop-filter: blur(5px);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }

        .modal-overlay.active {
            display: flex;
        }

        .modal {
            background: #1e1e2e;
            border-radius: 12px;
            padding: 30px;
            width: 90%;
            max-width: 500px;
            max-height: 90vh;
            overflow-y: auto;
        }

        .modal h2 {
            margin-bottom: 20px;
            font-size: 20px;
        }

        .form-group {
            margin-bottom: 15px;
        }

        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-size: 13px;
            color: #9e9e9e;
        }

        .form-group input,
        .form-group select,
        .form-group textarea {
            width: 100%;
            padding: 10px 15px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            color: #e0e0e0;
            font-size: 14px;
        }

        .form-group textarea {
            resize: vertical;
            min-height: 80px;
        }

        .modal-actions {
            display: flex;
            gap: 10px;
            justify-content: flex-end;
            margin-top: 20px;
        }

        /* Auto-refresh indicator */
        .auto-refresh {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            color: #9e9e9e;
        }

        .auto-refresh .indicator {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #81c784;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        /* Toast notification */
        .toast {
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 15px 25px;
            border-radius: 8px;
            color: white;
            font-size: 14px;
            font-weight: 500;
            transform: translateY(100px);
            opacity: 0;
            transition: all 0.3s ease;
            z-index: 2000;
        }

        .toast.show {
            transform: translateY(0);
            opacity: 1;
        }

        .toast.success {
            background: linear-gradient(135deg, #81c784, #66bb6a);
        }

        .toast.error {
            background: linear-gradient(135deg, #e57373, #ef5350);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Feature Flags Dashboard</h1>
            <p>Gerencie feature flags dinâmicas em tempo real</p>
        </div>

        <div class="stats" id="stats">
            <div class="stat-card">
                <div class="label">Total de Flags</div>
                <div class="value" id="total-flags">-</div>
            </div>
            <div class="stat-card">
                <div class="label">Flags Ativas</div>
                <div class="value" id="enabled-flags">-</div>
            </div>
            <div class="stat-card">
                <div class="label">Flags Inativas</div>
                <div class="value" id="disabled-flags">-</div>
            </div>
            <div class="stat-card">
                <div class="label">Gradual Rollout</div>
                <div class="value" id="gradual-flags">-</div>
            </div>
        </div>

        <div class="toolbar">
            <div class="search-box">
                <input type="text" id="search-input" placeholder="Buscar flags por nome ou tag...">
            </div>
            <div class="filters">
                <button class="btn btn-secondary" onclick="filterFlags('all')">Todas</button>
                <button class="btn btn-secondary" onclick="filterFlags('enabled')">Ativas</button>
                <button class="btn btn-secondary" onclick="filterFlags('disabled')">Inativas</button>
                <button class="btn btn-primary" onclick="openCreateModal()">+ Nova Flag</button>
            </div>
            <div class="auto-refresh">
                <div class="indicator"></div>
                Auto-refresh (30s)
            </div>
        </div>

        <div id="error-container"></div>

        <div class="flags-table">
            <table>
                <thead>
                    <tr>
                        <th>Nome</th>
                        <th>Descrição</th>
                        <th>Status</th>
                        <th>Estratégia</th>
                        <th>Owner</th>
                        <th>Toggle</th>
                        <th>Ações</th>
                    </tr>
                </thead>
                <tbody id="flags-body">
                    <tr>
                        <td colspan="7" class="loading">Carregando flags...</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- Create Modal -->
    <div class="modal-overlay" id="create-modal">
        <div class="modal">
            <h2>Criar Nova Feature Flag</h2>
            <form id="create-form" onsubmit="createFlag(event)">
                <div class="form-group">
                    <label>Nome *</label>
                    <input type="text" name="flag_name" required placeholder="ex: new_feature_v2" pattern="[a-z0-9_]+" title="Use apenas letras minúsculas, números e underscore">
                </div>
                <div class="form-group">
                    <label>Descrição</label>
                    <textarea name="description" placeholder="Descreva o propósito desta flag"></textarea>
                </div>
                <div class="form-group">
                    <label>Estratégia de Rollout</label>
                    <select name="rollout_strategy">
                        <option value="all">Todos (All)</option>
                        <option value="gradual">Gradual (Percentage)</option>
                        <option value="whitelist">Whitelist</option>
                        <option value="canary">Canary</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Owner</label>
                    <input type="text" name="owner" placeholder="ex: platform-team">
                </div>
                <div class="form-group">
                    <label>Tags (separadas por vírgula)</label>
                    <input type="text" name="tags" placeholder="ex: performance, experimental">
                </div>
                <div class="modal-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeCreateModal()">Cancelar</button>
                    <button type="submit" class="btn btn-primary">Criar Flag</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Edit Modal -->
    <div class="modal-overlay" id="edit-modal">
        <div class="modal">
            <h2>Editar Feature Flag</h2>
            <form id="edit-form" onsubmit="updateFlag(event)">
                <input type="hidden" name="flag_name" id="edit-flag-name">
                <div class="form-group">
                    <label>Descrição</label>
                    <textarea name="description" id="edit-description"></textarea>
                </div>
                <div class="form-group">
                    <label>Estratégia de Rollout</label>
                    <select name="rollout_strategy" id="edit-strategy">
                        <option value="all">Todos (All)</option>
                        <option value="gradual">Gradual (Percentage)</option>
                        <option value="whitelist">Whitelist</option>
                        <option value="canary">Canary</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Owner</label>
                    <input type="text" name="owner" id="edit-owner">
                </div>
                <div class="modal-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeEditModal()">Cancelar</button>
                    <button type="submit" class="btn btn-primary">Salvar Alterações</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Toast -->
    <div class="toast" id="toast"></div>

    <script>
        // API Base URL
        const API_BASE = '/admin/feature-flags/api';
        let allFlags = [];
        let currentFilter = 'all';
        let autoRefreshInterval;

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            loadFlags();
            setupSearch();
            startAutoRefresh();
        });

        // Load flags from API
        async function loadFlags() {
            try {
                const response = await fetch(`${API_BASE}/flags`);
                if (!response.ok) throw new Error('Failed to load flags');
                allFlags = await response.json();
                renderFlags();
                updateStats();
            } catch (error) {
                showError('Erro ao carregar flags: ' + error.message);
            }
        }

        // Render flags table
        function renderFlags() {
            const tbody = document.getElementById('flags-body');
            const searchTerm = document.getElementById('search-input').value.toLowerCase();

            let filtered = allFlags;
            if (currentFilter === 'enabled') {
                filtered = filtered.filter(f => f.enabled);
            } else if (currentFilter === 'disabled') {
                filtered = filtered.filter(f => !f.enabled);
            }

            if (searchTerm) {
                filtered = filtered.filter(f =>
                    f.flag_name.toLowerCase().includes(searchTerm) ||
                    (f.description && f.description.toLowerCase().includes(searchTerm)) ||
                    (f.tags && f.tags.some(t => t.toLowerCase().includes(searchTerm)))
                );
            }

            if (filtered.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" class="empty-state">
                            <svg viewBox="0 0 24 24" fill="currentColor">
                                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                            </svg>
                            <p>Nenhuma flag encontrada</p>
                        </td>
                    </tr>
                `;
                return;
            }

            tbody.innerHTML = filtered.map(flag => `
                <tr>
                    <td><strong>${escapeHtml(flag.flag_name)}</strong></td>
                    <td>${escapeHtml(flag.description || '-')}</td>
                    <td>
                        <span class="badge ${flag.enabled ? 'badge-enabled' : 'badge-disabled'}">
                            ${flag.enabled ? 'Ativa' : 'Inativa'}
                        </span>
                    </td>
                    <td>
                        <span class="badge badge-strategy">${escapeHtml(flag.rollout_strategy || 'all')}</span>
                    </td>
                    <td>${escapeHtml(flag.owner || '-')}</td>
                    <td>
                        <label class="toggle-switch">
                            <input type="checkbox" ${flag.enabled ? 'checked' : ''} onchange="toggleFlag('${flag.flag_name}')">
                            <span class="toggle-slider"></span>
                        </label>
                    </td>
                    <td>
                        <div class="actions">
                            <button class="btn btn-secondary btn-icon" onclick="openEditModal('${flag.flag_name}')">Editar</button>
                            <button class="btn btn-danger btn-icon" onclick="deleteFlag('${flag.flag_name}')">Excluir</button>
                        </div>
                    </td>
                </tr>
            `).join('');
        }

        // Update statistics
        function updateStats() {
            document.getElementById('total-flags').textContent = allFlags.length;
            document.getElementById('enabled-flags').textContent = allFlags.filter(f => f.enabled).length;
            document.getElementById('disabled-flags').textContent = allFlags.filter(f => !f.enabled).length;
            document.getElementById('gradual-flags').textContent = allFlags.filter(f => f.rollout_strategy === 'gradual').length;
        }

        // Toggle flag
        async function toggleFlag(flagName) {
            try {
                const response = await fetch(`${API_BASE}/flags/${encodeURIComponent(flagName)}/toggle`, {
                    method: 'POST'
                });
                if (!response.ok) throw new Error('Failed to toggle flag');
                const result = await response.json();
                showToast(result.message, 'success');
                await loadFlags();
            } catch (error) {
                showError('Erro ao fazer toggle: ' + error.message);
                await loadFlags(); // Reload to restore UI state
            }
        }

        // Create flag
        async function createFlag(event) {
            event.preventDefault();
            const form = event.target;
            const formData = new FormData(form);

            const data = {
                flag_name: formData.get('flag_name'),
                description: formData.get('description') || null,
                enabled: false,
                rollout_strategy: formData.get('rollout_strategy'),
                rollout_config: {},
                created_by: 'dashboard-user',
                owner: formData.get('owner') || null,
                tags: formData.get('tags') ? formData.get('tags').split(',').map(t => t.trim()) : []
            };

            try {
                const response = await fetch(`${API_BASE}/flags`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                if (!response.ok) throw new Error('Failed to create flag');
                showToast(`Flag "${data.flag_name}" criada com sucesso!`, 'success');
                closeCreateModal();
                form.reset();
                await loadFlags();
            } catch (error) {
                showError('Erro ao criar flag: ' + error.message);
            }
        }

        // Update flag
        async function updateFlag(event) {
            event.preventDefault();
            const form = event.target;
            const flagName = document.getElementById('edit-flag-name').value;

            const data = {
                description: document.getElementById('edit-description').value || null,
                rollout_strategy: document.getElementById('edit-strategy').value,
                owner: document.getElementById('edit-owner').value || null
            };

            try {
                const response = await fetch(`${API_BASE}/flags/${encodeURIComponent(flagName)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                if (!response.ok) throw new Error('Failed to update flag');
                showToast(`Flag "${flagName}" atualizada com sucesso!`, 'success');
                closeEditModal();
                await loadFlags();
            } catch (error) {
                showError('Erro ao atualizar flag: ' + error.message);
            }
        }

        // Delete flag
        async function deleteFlag(flagName) {
            if (!confirm(`Tem certeza que deseja excluir a flag "${flagName}"?`)) return;

            try {
                const response = await fetch(`${API_BASE}/flags/${encodeURIComponent(flagName)}`, {
                    method: 'DELETE'
                });
                if (!response.ok) throw new Error('Failed to delete flag');
                showToast(`Flag "${flagName}" excluída com sucesso!`, 'success');
                await loadFlags();
            } catch (error) {
                showError('Erro ao excluir flag: ' + error.message);
            }
        }

        // Filter flags
        function filterFlags(filter) {
            currentFilter = filter;
            renderFlags();
        }

        // Search setup
        function setupSearch() {
            const searchInput = document.getElementById('search-input');
            let debounceTimer;
            searchInput.addEventListener('input', () => {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(renderFlags, 300);
            });
        }

        // Auto-refresh
        function startAutoRefresh() {
            autoRefreshInterval = setInterval(loadFlags, 30000); // 30 seconds
        }

        // Modal functions
        function openCreateModal() {
            document.getElementById('create-modal').classList.add('active');
        }

        function closeCreateModal() {
            document.getElementById('create-modal').classList.remove('active');
        }

        function openEditModal(flagName) {
            const flag = allFlags.find(f => f.flag_name === flagName);
            if (!flag) return;

            document.getElementById('edit-flag-name').value = flag.flag_name;
            document.getElementById('edit-description').value = flag.description || '';
            document.getElementById('edit-strategy').value = flag.rollout_strategy || 'all';
            document.getElementById('edit-owner').value = flag.owner || '';
            document.getElementById('edit-modal').classList.add('active');
        }

        function closeEditModal() {
            document.getElementById('edit-modal').classList.remove('active');
        }

        // Close modals on overlay click
        document.querySelectorAll('.modal-overlay').forEach(overlay => {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    overlay.classList.remove('active');
                }
            });
        });

        // Toast notification
        function showToast(message, type = 'success') {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = `toast ${type} show`;
            setTimeout(() => {
                toast.classList.remove('show');
            }, 3000);
        }

        // Show error
        function showError(message) {
            const container = document.getElementById('error-container');
            container.innerHTML = `<div class="error">${escapeHtml(message)}</div>`;
            setTimeout(() => {
                container.innerHTML = '';
            }, 5000);
        }

        // Escape HTML
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    </script>
</body>
</html>
"""


# =============================================================================
# Router Factory
# =============================================================================


def create_dashboard_router(feature_flag_service: Any) -> APIRouter:
    """
    Cria router FastAPI para dashboard de feature flags.

    Args:
        feature_flag_service: Instância de FeatureFlagService

    Returns:
        APIRouter configurado com endpoints da UI
    """
    router = APIRouter(prefix="/admin/feature-flags", tags=["Admin UI"])

    # -------------------------------------------------------------------------
    # GET /admin/feature-flags - Dashboard HTML
    # -------------------------------------------------------------------------

    @router.get(
        "",
        response_class=HTMLResponse,
        summary="Feature Flags Dashboard",
        description="Retorna interface web para gestão de feature flags.",
    )
    async def get_dashboard():
        """
        Retorna o dashboard HTML para gestão de feature flags.

        A interface inclui:
        - Lista de flags com status
        - Botões para toggle enable/disable
        - Formulário para criar nova flag
        - Auto-refresh a cada 30 segundos
        """
        return HTMLResponse(content=DASHBOARD_HTML)

    # -------------------------------------------------------------------------
    # GET /admin/feature-flags/api/flags - Listar flags (JSON)
    # -------------------------------------------------------------------------

    @router.get(
        "/api/flags",
        summary="Listar flags (JSON)",
        description="Retorna todas as flags em formato JSON para consumo via AJAX.",
    )
    async def list_flags_api(
        enabled: bool | None = None,
    ):
        """
        Lista todas as feature flags em formato JSON.

        Usado pelo dashboard via AJAX para carregar dados.
        """
        try:
            return await feature_flag_service.list_flags(
                enabled_only=enabled if enabled is not None else False
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao listar flags: {e!s}",
            ) from e

    # -------------------------------------------------------------------------
    # POST /admin/feature-flags/api/flags/{name}/toggle - Toggle flag
    # -------------------------------------------------------------------------

    @router.post(
        "/api/flags/{name}/toggle",
        response_model=ToggleResponse,
        summary="Toggle flag (JSON)",
        description="Alterna o estado de uma feature flag.",
    )
    async def toggle_flag_api(name: str):
        """
        Alterna o estado de uma feature flag.

        Endpoint usado pelo dashboard para toggle via botão.
        """
        flag = await feature_flag_service.get_flag(name)

        if not flag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Flag '{name}' não encontrada",
            )

        previous_state = flag.get("enabled", False)
        new_state = not previous_state

        flag["enabled"] = new_state
        await feature_flag_service.set_flag(name, flag)

        action = "ativada" if new_state else "desativada"

        return ToggleResponse(
            flag_name=name,
            enabled=new_state,
            previous_state=previous_state,
            message=f"Flag '{name}' foi {action} com sucesso.",
        )

    # -------------------------------------------------------------------------
    # POST /admin/feature-flags/api/flags - Criar flag
    # -------------------------------------------------------------------------

    @router.post(
        "/api/flags",
        status_code=status.HTTP_201_CREATED,
        summary="Criar flag (JSON)",
        description="Cria uma nova feature flag via dashboard.",
    )
    async def create_flag_api(payload: DashboardFlagCreate):
        """
        Cria uma nova feature flag via dashboard.

        Endpoint usado pelo formulário de criação.
        """
        try:
            flag_data = payload.model_dump(exclude_unset=True)

            # Criar flag via serviço
            await feature_flag_service.set_flag(payload.flag_name, flag_data)

            # Buscar flag completa
            flag = await feature_flag_service.get_flag(payload.flag_name)
            if not flag:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Falha ao criar flag",
                )

            return flag

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao criar flag: {e!s}",
            ) from e

    # -------------------------------------------------------------------------
    # PUT /admin/feature-flags/api/flags/{name} - Atualizar flag
    # -------------------------------------------------------------------------

    @router.put(
        "/api/flags/{name}",
        summary="Atualizar flag (JSON)",
        description="Atualiza uma feature flag via dashboard.",
    )
    async def update_flag_api(name: str, payload: DashboardFlagUpdate):
        """
        Atualiza uma feature flag via dashboard.

        Endpoint usado pelo formulário de edição.
        """
        # Verificar se flag existe
        existing = await feature_flag_service.get_flag(name)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Flag '{name}' não encontrada",
            )

        try:
            update_data = payload.model_dump(exclude_unset=True, exclude_none=True)
            flag_data = {**existing, **update_data}

            await feature_flag_service.set_flag(name, flag_data)

            # Buscar flag atualizada
            return await feature_flag_service.get_flag(name)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao atualizar flag: {e!s}",
            ) from e

    # -------------------------------------------------------------------------
    # DELETE /admin/feature-flags/api/flags/{name} - Deletar flag
    # -------------------------------------------------------------------------

    @router.delete(
        "/api/flags/{name}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Deletar flag (JSON)",
        description="Remove uma feature flag via dashboard.",
    )
    async def delete_flag_api(name: str):
        """
        Remove uma feature flag via dashboard.

        Endpoint usado pelo botão de exclusão.
        """
        deleted = await feature_flag_service.delete_flag(name)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Flag '{name}' não encontrada",
            )

    return router
