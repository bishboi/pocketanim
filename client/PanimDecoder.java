/*
 * Reference decoder for the pocketanim IR, in plain Java.
 *
 * This is the first piece of the client half. It exists to prove the binary
 * format is portable rather than an artefact of the Python that writes it --
 * if this and exporter/decode.py disagree, the format is underspecified.
 *
 * Deliberately dependency-free and allocation-obvious: the Android renderer
 * will be this logic in Kotlin, feeding android.graphics.Path objects instead
 * of printing statistics. No Android APIs are used here, so it runs and can be
 * checked on any JVM.
 *
 *   javac client/PanimDecoder.java -d /tmp/panim
 *   java -cp /tmp/panim PanimDecoder scene.panm [frame] [--dump]
 */

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PanimDecoder {

    private static final int MAGIC = 0x4D4E4150; // "PANM" little-endian
    private static final int FLAG_CAMERA = 1;
    private static final int SHADE_IN_3D = 1;
    private static final int CAMERA_FLOATS = 17;
    private static final int REC_SNAPSHOT = 0;
    private static final java.util.Locale LOCALE = java.util.Locale.ROOT;

    public static final class Instance {
        public int slot;
        public int atlasId;
        public int flags;
        public final float[] transform = new float[12]; // row-major 3x4
        public final int[] fill = new int[4];
        public final int[] stroke = new int[4];
        public float strokeWidth;
        public float[] normal; // null unless SHADE_IN_3D
    }

    public static final class Record {
        public int kind;
        public Instance[] instances;
    }

    public final int fps;
    public final float[] lo = new float[3];
    public final float[] hi = new float[3];
    public final float[][] atlas;      // per shape: flat xyz triples, dequantised
    public final float[][] cameras;    // null when the scene is 2D
    public final Record[] records;

    private PanimDecoder(int fps, float[][] atlas, float[][] cameras, Record[] records,
                         float[] lo, float[] hi) {
        this.fps = fps;
        this.atlas = atlas;
        this.cameras = cameras;
        this.records = records;
        System.arraycopy(lo, 0, this.lo, 0, 3);
        System.arraycopy(hi, 0, this.hi, 0, 3);
    }

    public static PanimDecoder parse(byte[] bytes) {
        ByteBuffer buf = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);

        if (buf.getInt() != MAGIC) {
            throw new IllegalArgumentException("not a pocketanim IR");
        }
        int version = Short.toUnsignedInt(buf.getShort());
        int flags = Short.toUnsignedInt(buf.getShort());
        int fps = Short.toUnsignedInt(buf.getShort());
        int recordCount = buf.getInt();
        int atlasCount = buf.getInt();

        float[] lo = {buf.getFloat(), buf.getFloat(), buf.getFloat()};
        float[] hi = {buf.getFloat(), buf.getFloat(), buf.getFloat()};

        float[] span = new float[3];
        for (int i = 0; i < 3; i++) {
            float d = hi[i] - lo[i];
            span[i] = Math.abs(d) < 1e-9f ? 1.0f : d;
        }

        float[][] cameras = null;
        if ((flags & FLAG_CAMERA) != 0) {
            cameras = new float[recordCount][CAMERA_FLOATS];
            for (int r = 0; r < recordCount; r++) {
                for (int c = 0; c < CAMERA_FLOATS; c++) {
                    cameras[r][c] = buf.getFloat();
                }
            }
        }

        // Atlas geometry is quantised to uint16 over the scene bounding box.
        float[][] atlas = new float[atlasCount][];
        for (int s = 0; s < atlasCount; s++) {
            int pointCount = buf.getInt();
            float[] points = new float[pointCount * 3];
            for (int p = 0; p < pointCount; p++) {
                for (int axis = 0; axis < 3; axis++) {
                    int raw = Short.toUnsignedInt(buf.getShort());
                    points[p * 3 + axis] = lo[axis] + (raw / 65535.0f) * span[axis];
                }
            }
            atlas[s] = points;
        }

        Record[] records = new Record[recordCount];
        for (int r = 0; r < recordCount; r++) {
            Record record = new Record();
            record.kind = Byte.toUnsignedInt(buf.get());
            int instanceCount = buf.getInt();
            record.instances = new Instance[instanceCount];

            for (int i = 0; i < instanceCount; i++) {
                Instance inst = new Instance();
                inst.slot = buf.getInt();
                inst.atlasId = buf.getInt();
                inst.flags = Byte.toUnsignedInt(buf.get());

                // Linear part is float16; translation stays float32 because at
                // 720p half precision would be visible in position.
                for (int k = 0; k < 9; k++) {
                    int row = k / 3, col = k % 3;
                    inst.transform[row * 4 + col] = Float.float16ToFloat(buf.getShort());
                }
                for (int row = 0; row < 3; row++) {
                    inst.transform[row * 4 + 3] = buf.getFloat();
                }

                for (int k = 0; k < 4; k++) inst.fill[k] = Byte.toUnsignedInt(buf.get());
                for (int k = 0; k < 4; k++) inst.stroke[k] = Byte.toUnsignedInt(buf.get());
                inst.strokeWidth = Short.toUnsignedInt(buf.getShort()) / 64.0f;

                if ((inst.flags & SHADE_IN_3D) != 0) {
                    inst.normal = new float[3];
                    for (int k = 0; k < 3; k++) {
                        inst.normal[k] = Float.float16ToFloat(buf.getShort());
                    }
                }
                record.instances[i] = inst;
            }
            records[r] = record;
        }

        if (version != 1) {
            System.err.println("warning: unexpected IR version " + version);
        }
        return new PanimDecoder(fps, atlas, cameras, records, lo, hi);
    }

    /**
     * Resolve a frame to its ordered instance list: walk back to the preceding
     * snapshot and replay keyframes forward. Keyframes hold absolute values, so
     * replay is an overwrite and never accumulates -- which is what makes
     * seeking exact rather than approximate.
     */
    public Instance[] frame(int index) {
        int start = index;
        while (start > 0 && records[start].kind != REC_SNAPSHOT) {
            start--;
        }

        java.util.List<Integer> order = new java.util.ArrayList<>();
        java.util.Map<Integer, Instance> state = new java.util.HashMap<>();

        for (int r = start; r <= index; r++) {
            Record record = records[r];
            if (record.kind == REC_SNAPSHOT) {
                order.clear();
                state.clear();
                for (Instance inst : record.instances) {
                    order.add(inst.slot);
                    state.put(inst.slot, inst);
                }
            } else {
                for (Instance inst : record.instances) {
                    if (!state.containsKey(inst.slot)) order.add(inst.slot);
                    state.put(inst.slot, inst);
                }
            }
        }

        java.util.List<Instance> out = new java.util.ArrayList<>(order.size());
        for (int slot : order) {
            Instance inst = state.get(slot);
            if (inst != null) out.add(inst);
        }
        return out.toArray(new Instance[0]);
    }

    /**
     * Canonical text dump, for cross-checking against exporter/decode.py.
     *
     * Every line is one field group, so a disagreement names the structure that
     * disagrees instead of just "the bytes differ". Floats print at a fixed
     * width: the two decoders dequantise at different precision (float32 here,
     * float64 there) and that is deliberate, so the comparison is by tolerance.
     */
    public void dump(int probe, java.io.PrintStream out) {
        out.printf(LOCALE, "H %d %d %d %d%n", fps, records.length, atlas.length,
                cameras != null ? 1 : 0);
        out.printf(LOCALE, "B %.6f %.6f %.6f %.6f %.6f %.6f%n",
                lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]);

        for (int s = 0; s < atlas.length; s++) {
            float[] pts = atlas[s];
            int n = pts.length / 3;
            double[] mean = new double[3];
            for (int i = 0; i < n; i++) {
                for (int k = 0; k < 3; k++) mean[k] += pts[i * 3 + k];
            }
            for (int k = 0; k < 3; k++) mean[k] = n > 0 ? mean[k] / n : 0.0;
            out.printf(LOCALE, "A %d %d %.6f %.6f %.6f %.6f %.6f %.6f %.6f %.6f %.6f%n",
                    s, n,
                    n > 0 ? pts[0] : 0.0, n > 0 ? pts[1] : 0.0, n > 0 ? pts[2] : 0.0,
                    n > 0 ? pts[(n - 1) * 3] : 0.0,
                    n > 0 ? pts[(n - 1) * 3 + 1] : 0.0,
                    n > 0 ? pts[(n - 1) * 3 + 2] : 0.0,
                    mean[0], mean[1], mean[2]);
        }

        for (int r = 0; r < records.length; r++) {
            out.printf(LOCALE, "R %d %d %d%n", r, records[r].kind, records[r].instances.length);
        }

        if (cameras != null) {
            StringBuilder line = new StringBuilder("C " + probe);
            for (float v : cameras[probe]) line.append(String.format(LOCALE, " %.6f", v));
            out.println(line);
        }

        Instance[] frame = frame(probe);
        out.printf(LOCALE, "F %d %d%n", probe, frame.length);
        for (int i = 0; i < frame.length; i++) {
            Instance inst = frame[i];
            StringBuilder line = new StringBuilder();
            line.append(String.format(LOCALE, "I %d %d %d %d", i, inst.slot, inst.atlasId, inst.flags));
            for (int row = 0; row < 3; row++) {
                for (int col = 0; col < 4; col++) {
                    line.append(String.format(LOCALE, " %.6f", inst.transform[row * 4 + col]));
                }
            }
            for (int k = 0; k < 4; k++) line.append(" ").append(inst.fill[k]);
            for (int k = 0; k < 4; k++) line.append(" ").append(inst.stroke[k]);
            line.append(String.format(LOCALE, " %.6f", inst.strokeWidth));
            if (inst.normal != null) {
                for (int k = 0; k < 3; k++) line.append(String.format(LOCALE, " %.6f", inst.normal[k]));
            }
            out.println(line);
        }
    }

    public static void main(String[] args) throws IOException {
        PanimDecoder ir = parse(Files.readAllBytes(Path.of(args[0])));
        int probe = args.length > 1 ? Integer.parseInt(args[1]) : ir.records.length / 2;

        if (args.length > 2 && args[2].equals("--dump")) {
            ir.dump(probe, System.out);
            return;
        }

        int atlasPoints = 0;
        for (float[] shape : ir.atlas) atlasPoints += shape.length / 3;

        System.out.println("fps            " + ir.fps);
        System.out.println("records        " + ir.records.length);
        System.out.println("atlas_shapes   " + ir.atlas.length);
        System.out.println("atlas_points   " + atlasPoints);
        System.out.println("has_camera     " + (ir.cameras != null));

        Instance[] frame = ir.frame(probe);
        System.out.println("frame          " + probe);
        System.out.println("instances      " + frame.length);

        if (frame.length > 0) {
            Instance first = frame[0];
            System.out.printf("first_atlas_id %d%n", first.atlasId);
            System.out.printf("first_fill     %d,%d,%d,%d%n",
                    first.fill[0], first.fill[1], first.fill[2], first.fill[3]);
            System.out.printf("first_tx       %.6f,%.6f,%.6f%n",
                    first.transform[3], first.transform[7], first.transform[11]);
        }
    }
}
