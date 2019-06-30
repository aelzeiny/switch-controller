import os
import signal
import psutil
import errno
import subprocess


def reap_process_group(pid, sig=signal.SIGTERM, timeout=60):
    """
    Note: Shamelessly Stolen from Apache-Airflow...

    Tries really hard to terminate all children (including grandchildren). Will send
    sig (SIGTERM) to the process group of pid. If any process is alive after timeout
    a SIGKILL will be send.

    :param log: log handler
    :param pid: pid to kill
    :param sig: signal type
    :param timeout: how much time a process has to terminate
    """

    def on_terminate(p):
        print("Process %s (%s) terminated with exit code %s" % (p, p.pid, p.returncode))

    if pid == os.getpid():
        raise RuntimeError("I refuse to kill myself")

    parent = psutil.Process(pid)

    children = parent.children(recursive=True)
    children.append(parent)

    try:
        pg = os.getpgid(pid)
    except OSError as err:
        # Skip if not such process - we experience a race and it just terminated
        if err.errno == errno.ESRCH:
            return
        raise

    print("Sending %s to GPID %s" % (sig, pg))
    os.killpg(os.getpgid(pid), sig)

    gone, alive = psutil.wait_procs(children, timeout=timeout, callback=on_terminate)

    if alive:
        for p in alive:
            print("process %s (%s) did not respond to SIGTERM. Trying SIGKILL", p, pid)

        os.killpg(os.getpgid(pid), signal.SIGKILL)

        gone, alive = psutil.wait_procs(alive, timeout=timeout, callback=on_terminate)
        if alive:
            for p in alive:
                print("Process %s (%s) could not be killed. Giving up." % (p, p.pid))


def start_webcam_recording(file):
    cmd = [
        'ffmpeg',
        '-video_size',
        '1280x720',
        '-framerate',
        '30',
        '-f',
        'avfoundation',
        '-i',
        '"default"',
        file
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        close_fds=True,
        env=os.environ.copy(),
        preexec_fn=os.setsid
    )

    return proc


def stop_webcam_recording(proc):
    reap_process_group(proc.pid)


def get_recorder_functions(filename):
    """
    Returns 2 functions that will start & stop recording to a filename & take no parameters
    :return:
    """
    proc = None

    def start_webcam():
        nonlocal proc
        proc = start_webcam_recording(filename)

    def stop_webcam():
        stop_webcam_recording(proc)
    return start_webcam, stop_webcam


if __name__ == '__main__':
    import time
    start, stop = get_recorder_functions('example.mpg')
    print('Starting Recording')
    start()
    time.sleep(10)
    print('Stopping Recording')
    stop()

