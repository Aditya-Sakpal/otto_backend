import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.services.call_service import CallService
print('has get_call_logs:', hasattr(CallService, 'get_call_logs'))

