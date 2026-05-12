export default class Level2 extends Phaser.Scene {
    constructor() {
        super('Level2');
    }

    preload() {
        this.load.image('library_tile', 'assets/library_tile.png');
        this.load.svg('dolphin', 'assets/dolphin.svg');
        this.load.svg('heart', 'assets/heart.svg');
    }

    create() {
        this.add.tileSprite(400, 300, 800, 600, 'library_tile').setAlpha(0.7);

        this.player = this.physics.add.sprite(400, 300, 'dolphin');
        this.player.setCollideWorldBounds(true);
        this.player.setScale(0.8);

        // Sokoban Blocks
        this.blocks = this.physics.add.group();
        this.targets = this.add.group();

        const data = [
            { x: 250, y: 200, tx: 550, ty: 200, memory: "Our First Kiss" },
            { x: 250, y: 400, tx: 550, ty: 400, memory: "That Rainy Day" },
            { x: 350, y: 300, tx: 450, ty: 300, memory: "The Surprise Date" }
        ];

        data.forEach((d, i) => {
            const target = this.add.image(d.tx, d.ty, 'heart').setScale(0.4).setAlpha(0.3);
            this.targets.add(target);

            // Using graphics for blocks but embedding the heart SVG
            const block = this.add.container(d.x, d.y);
            const rect = this.add.rectangle(0, 0, 80, 80, 0x6c5ce7, 1);
            rect.setStrokeStyle(4, 0xffffff);
            const icon = this.add.image(0, 0, 'heart').setScale(0.3);
            block.add([rect, icon]);
            
            this.physics.add.existing(block);
            block.body.setCollideWorldBounds(true);
            block.body.setDrag(800);
            block.body.setDamping(false);
            block.body.setMass(10);
            block.body.setPushable(true);
            block.memory = d.memory;
            this.blocks.add(block);
        });

        this.physics.add.collider(this.player, this.blocks);
        this.physics.add.collider(this.blocks, this.blocks);

        this.cursors = this.input.keyboard.createCursorKeys();
        this.cameras.main.fadeIn(1000);
        this.events.emit('show-dialogue', "Level 2: Memory Blocks\nPush the memories onto the hearts to unlock Level 3.");
    }

    update() {
        this.player.setVelocity(0);
        const speed = 300; // Even faster for pushing force

        if (this.cursors.left.isDown) this.player.setVelocityX(-speed);
        else if (this.cursors.right.isDown) this.player.setVelocityX(speed);

        if (this.cursors.up.isDown) this.player.setVelocityY(-speed);
        else if (this.cursors.down.isDown) this.player.setVelocityY(speed);

        // Check win condition
        let allOnTarget = true;
        this.blocks.getChildren().forEach((block, i) => {
            const target = this.targets.getChildren()[i];
            const dist = Phaser.Math.Distance.Between(block.x, block.y, target.x, target.y);
            
            if (dist < 40) {
                target.setAlpha(1).setScale(0.5);
                if (dist < 10) {
                    block.x = target.x;
                    block.y = target.y;
                    block.body.setVelocity(0);
                }
            } else {
                target.setAlpha(0.3).setScale(0.4);
                allOnTarget = false;
            }
        });

        if (allOnTarget && !this.won) {
            this.won = true;
            this.events.emit('show-dialogue', "Memories restored!\nPreparing final level...");
            this.cameras.main.fadeOut(1000);
            this.time.delayedCall(1500, () => {
                this.scene.start('Level3');
            });
        }
    }
}
