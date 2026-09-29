/**
 * The keyboard hint line. Markup from reference/ontaix-studio-reference.html line 233, without
 * the `Space next` and `R restart` shortcuts.
 */
export function Hint() {
  return (
    <div className="hint">
      <kbd>P</kbd> changes &nbsp; <kbd>D</kbd> domains &nbsp; <kbd>I</kbd> import · drop a file &nbsp; <kbd>C</kbd> coverage &nbsp; <kbd>A</kbd> arrange &nbsp; <kbd>S</kbd> skip animation &nbsp; <kbd>click</kbd> new concept · <kbd>drop on a cell</kbd> relate &nbsp; <kbd>wheel</kbd> zoom &nbsp; <kbd>F</kbd> full screen
    </div>
  );
}
