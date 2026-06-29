import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button
import argparse

def simulate_pid(Kp, Ki, Kd, setpoint=1.0, dt=0.05, steps=200):
    """Mô phỏng vòng lặp PID cơ bản"""
    t = np.arange(0, steps*dt, dt)
    y = np.zeros(steps)
    e = np.zeros(steps)
    integral = 0
    prev_error = 0
    
    velocity = 0
    
    for i in range(1, steps):
        error = setpoint - y[i-1]
        integral += error * dt
        derivative = (error - prev_error) / dt
        
        control = Kp * error + Ki * integral + Kd * derivative
        
        acceleration = control - 0.5 * velocity
        velocity += acceleration * dt
        y[i] = y[i-1] + velocity * dt
        
        e[i] = error
        prev_error = error
        
    return t, y, e

def main():
    fig, ax = plt.subplots(figsize=(10, 6))
    plt.subplots_adjust(left=0.1, bottom=0.35)
    
    t, y, _ = simulate_pid(1.0, 0.1, 0.05)
    line, = ax.plot(t, y, lw=2, label='System Response')
    ax.axhline(1.0, color='r', linestyle='--', label='Setpoint')
    ax.set_ylim(-0.5, 2.5)
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Amplitude')
    ax.set_title('Interactive PID Tuning Simulation')
    ax.legend()
    ax.grid(True)

    axcolor = 'lightgoldenrodyellow'
    ax_kp = plt.axes([0.15, 0.2, 0.65, 0.03], facecolor=axcolor)
    ax_ki = plt.axes([0.15, 0.15, 0.65, 0.03], facecolor=axcolor)
    ax_kd = plt.axes([0.15, 0.1, 0.65, 0.03], facecolor=axcolor)

    s_kp = Slider(ax_kp, 'Kp', 0.0, 5.0, valinit=1.0)
    s_ki = Slider(ax_ki, 'Ki', 0.0, 2.0, valinit=0.1)
    s_kd = Slider(ax_kd, 'Kd', 0.0, 2.0, valinit=0.05)

    def update(val):
        kp = s_kp.val
        ki = s_ki.val
        kd = s_kd.val
        _, y_new, _ = simulate_pid(kp, ki, kd)
        line.set_ydata(y_new)
        fig.canvas.draw_idle()

    s_kp.on_changed(update)
    s_ki.on_changed(update)
    s_kd.on_changed(update)

    resetax = plt.axes([0.8, 0.025, 0.1, 0.04])
    button = Button(resetax, 'Reset', color=axcolor, hovercolor='0.975')

    def reset(event):
        s_kp.reset()
        s_ki.reset()
        s_kd.reset()
    button.on_clicked(reset)

    plt.show()

if __name__ == "__main__":
    print("Mở cửa sổ đồ họa để tinh chỉnh PID tương tác...")
    main()
