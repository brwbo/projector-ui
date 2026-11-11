import android.os.SystemClock;
import android.view.InputDevice;
import android.view.KeyEvent;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.reflect.Method;

public class Inj {
    public static void main(String[] args) throws Exception {
        Class<?> imClass = Class.forName("android.hardware.input.InputManager");
        Object im = imClass.getDeclaredMethod("getInstance").invoke(null);
        Method inject = imClass.getMethod("injectInputEvent", android.view.InputEvent.class, int.class);
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in));
        System.out.println("ready");
        System.out.flush();
        String line;
        while ((line = in.readLine()) != null) {
            line = line.trim();
            if (line.isEmpty()) continue;
            int code;
            try {
                code = Integer.parseInt(line);
            } catch (NumberFormatException e) {
                System.out.println("bad");
                System.out.flush();
                continue;
            }
            long now = SystemClock.uptimeMillis();
            KeyEvent down = new KeyEvent(now, now, KeyEvent.ACTION_DOWN, code, 0, 0, -1, 0, 0, InputDevice.SOURCE_KEYBOARD);
            KeyEvent up = new KeyEvent(now, now, KeyEvent.ACTION_UP, code, 0, 0, -1, 0, 0, InputDevice.SOURCE_KEYBOARD);
            inject.invoke(im, down, 0);
            inject.invoke(im, up, 0);
            System.out.println("ok");
            System.out.flush();
        }
    }
}
