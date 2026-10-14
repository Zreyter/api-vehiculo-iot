class ServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class DatabaseUnavailable(ServiceError):
    def __init__(self):
        super().__init__(503, "MySQL no está disponible o sus procedimientos no cumplen el contrato. Revisa la configuración y ejecuta el diagnóstico local.")
