from trame.widgets import vuetify3 as v
import inspect

# Check how events are bound in trame — look at AbstractElement.event processing
src = inspect.getsource(v.VSlider)
# Find how end event is registered
for i, line in enumerate(src.splitlines()):
    if 'end' in line.lower() or 'event' in line.lower():
        print(f"{i}: {line}")
