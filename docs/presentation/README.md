# hyper2kvm Presentation Materials

Quick reference documents for presentations and demos.

## Documents

### 📊 [Quick Comparison](quick-comparison.md)
**One-page overview** - Perfect for slides or quick demos
- Simple side-by-side comparison
- Visual workflow diagrams
- Quick command examples
- **Use for:** 5-minute presentations

### 📈 [Daemon vs CLI Workflow](daemon-vs-cli-workflow.md)
**Detailed architecture** - Complete technical overview
- Architecture diagrams
- Decision matrix
- Production deployment examples
- Pipeline comparisons
- **Use for:** Technical deep-dives, architecture reviews

## Viewing Diagrams

These documents use Mermaid diagrams. View them in:
- **GitHub**: Renders automatically
- **VS Code**: Install "Markdown Preview Mermaid Support" extension
- **Online**: Copy to https://mermaid.live/

## Quick Reference

### CLI Mode
```bash
hyper2kvm local --source vm.vmdk --output vm.qcow2
```
- Interactive, manual execution
- Single VM focus
- Development/testing

### Daemon Mode
```bash
systemctl start hyper2kvm.service
cp *.vmdk /var/lib/hyper2kvm/queue/
```
- Automated, continuous processing
- Batch operations
- Production deployments

## Presentation Tips

1. **Start with** `quick-comparison.md` for non-technical audiences
2. **Deep dive with** `daemon-vs-cli-workflow.md` for technical teams
3. **Demo flow**: Show CLI first, then daemon automation
4. **Key message**: One tool, two modes - flexibility for all use cases
